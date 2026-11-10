"""Quarto: zona do leito, estado do paciente por quadro, queda e ausência (RF-04).

``calcular_estados`` resume cada quadro em poucos números (quadril, inclinação
do tronco, tamanho do corpo, no leito ou não, velocidade). A queda e a
ausência saem daqui (``Fonte.VIDEO``); saída do leito, imobilidade e
agitação saem de ``monitor.movimentacao.detector`` a partir dos mesmos estados.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np

from monitor.eventos import Evento, Fonte, Severidade
from monitor.video.config import ConfigQuarto
from monitor.video.geometria import (
    ampliar_caixa,
    centro_quadril,
    deslocamento_medio,
    inclinacao_tronco,
    ponto_no_poligono,
    tamanho_corpo,
)
from monitor.video.tipos import Pessoa, Poligono, QuadroAnalisado

DETECTOR = "video.quarto/v1"


def estimar_zona(quadros: Sequence[QuadroAnalisado], cfg: ConfigQuarto = ConfigQuarto()) -> Poligono | None:
    """Mediana das caixas ``bed`` dos primeiros ``zona_s`` segundos, ampliada; senão o polígono do config."""
    caixas = [o.caixa for q in quadros if q.t_s <= cfg.zona_s for o in q.objetos if o.classe == "bed"]
    if caixas:
        mediana = tuple(float(v) for v in np.median(np.array(caixas), axis=0))
        x1, y1, x2, y2 = ampliar_caixa(mediana, cfg.ampliacao_leito)
        return ((x1, y1), (x2, y1), (x2, y2), (x1, y2))
    return cfg.poligono_leito


@dataclass(frozen=True)
class EstadoQuadro:
    t_s: float
    presente: bool
    quadril: np.ndarray  # (x, y) em px; NaN se ausente
    inclinacao: float  # graus do tronco em relação à vertical
    tamanho: float  # px, maior lado da caixa
    no_leito: bool | None  # quadril dentro da zona; ausente conta como fora; None sem zona
    movimento: float  # corpos/s desde o quadro anterior (NaN se o anterior não tinha paciente)


def calcular_estados(
    quadros: Sequence[QuadroAnalisado],
    pacientes: Sequence[Pessoa | None],
    zona: Poligono | None,
) -> list[EstadoQuadro]:
    estados: list[EstadoQuadro] = []
    anterior: tuple[float, Pessoa] | None = None
    for q, p in zip(quadros, pacientes):
        if p is None:
            estados.append(EstadoQuadro(q.t_s, False, np.array([np.nan, np.nan]), float("nan"),
                                        float("nan"), None if zona is None else False, float("nan")))
            anterior = None
            continue
        quadril = centro_quadril(p.pontos)
        tamanho = tamanho_corpo(p.caixa)
        movimento = float("nan")
        if anterior is not None and q.t_s > anterior[0]:
            movimento = deslocamento_medio(anterior[1].pontos, p.pontos, tamanho) / (q.t_s - anterior[0])
        no_leito = None if zona is None else ponto_no_poligono(quadril, zona)
        estados.append(EstadoQuadro(q.t_s, True, quadril, inclinacao_tronco(p.pontos), tamanho, no_leito, movimento))
        anterior = (q.t_s, p)
    return estados


def _evento(paciente_id: str, inicio: datetime, t_s: float, tipo: str, severidade: Severidade,
            descricao: str, valor: float) -> Evento:
    return Evento(paciente_id, inicio + timedelta(seconds=t_s), Fonte.VIDEO, tipo, severidade,
                  descricao, DETECTOR, round(float(valor), 3))


def detectar_quedas(
    estados: Sequence[EstadoQuadro],
    paciente_id: str,
    inicio: datetime,
    cfg: ConfigQuarto = ConfigQuarto(),
) -> list[Evento]:
    """Queda = quatro condições juntas no mesmo quadro:

    1. tronco a mais de ``queda_inclinacao_graus`` da vertical;
    2. quadril desceu mais de ``queda_descida_corpos`` × tamanho do corpo em até ``queda_janela_s``;
    3. quadril fora da zona do leito;
    4. nos ``queda_permanencia_s`` seguintes continua horizontal ou baixo.

    A condição 2 é a que separa queda de deitar devagar; a 3 separa de
    despencar na própria cama.
    """
    eventos: list[Evento] = []
    ultima_queda = float("-inf")
    for i, e in enumerate(estados):
        if not e.presente or e.no_leito or not e.inclinacao > cfg.queda_inclinacao_graus:
            continue
        if e.t_s - ultima_queda < cfg.queda_refratario_s:
            continue
        # 2. maior descida em relação a algum quadro da janela anterior
        melhor: tuple[float, EstadoQuadro] | None = None
        for r in estados[:i]:
            if r.presente and e.t_s - r.t_s <= cfg.queda_janela_s + 1e-9 and not np.isnan(r.quadril[1]):
                descida = (e.quadril[1] - r.quadril[1]) / r.tamanho
                if melhor is None or descida > melhor[0]:
                    melhor = (descida, r)
        if melhor is None or not melhor[0] > cfg.queda_descida_corpos:
            continue
        descida, ref = melhor
        # 4. permanece baixo ou horizontal até o fim da janela de permanência
        fim_janela = e.t_s + cfg.queda_permanencia_s - 1e-9
        confirmacao = next((k for k in estados[i + 1:] if k.t_s >= fim_janela), None)
        if confirmacao is None or not confirmacao.presente:
            continue  # o vídeo acabou (ou o paciente sumiu) antes de confirmar
        depois = [k for k in estados[i + 1:] if k.presente and k.t_s <= confirmacao.t_s]
        # Quadro com o paciente mas sem quadril nem tronco medidos (pontos incertos) não conta contra.
        medidos = [k for k in depois if not (np.isnan(k.inclinacao) and np.isnan(k.quadril[1]))]
        baixo = bool(medidos) and all(
            k.inclinacao > cfg.queda_inclinacao_graus
            or (k.quadril[1] - ref.quadril[1]) / ref.tamanho > cfg.queda_descida_corpos
            for k in medidos
        )
        if not baixo:
            continue
        ultima_queda = e.t_s
        eventos.append(_evento(
            paciente_id, inicio, e.t_s, "queda", Severidade.MAXIMA,
            f"Queda: tronco a {e.inclinacao:.0f}° da vertical e quadril desceu {descida:.2f} do tamanho do corpo "
            f"em {e.t_s - ref.t_s:.1f} s, fora do leito; continua no chão.",
            descida,
        ))
    return eventos


def detectar_ausencia(
    estados: Sequence[EstadoQuadro],
    paciente_id: str,
    inicio: datetime,
    cfg: ConfigQuarto = ConfigQuarto(),
) -> list[Evento]:
    """Um evento por trecho sem paciente de pelo menos ``ausencia_s``; valor = duração do trecho."""
    eventos: list[Evento] = []
    comeco: float | None = None
    for e in list(estados) + [None]:  # None fecha o último trecho
        if e is not None and not e.presente:
            comeco = e.t_s if comeco is None else comeco
            continue
        if comeco is not None:
            fim = e.t_s if e is not None else estados[-1].t_s
            if fim - comeco >= cfg.ausencia_s:
                eventos.append(_evento(paciente_id, inicio, comeco, "paciente_ausente", Severidade.INFO,
                                       f"Ninguém no quadro por {fim - comeco:.0f} s.", fim - comeco))
            comeco = None
    return eventos
