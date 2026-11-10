"""Eventos de movimentação (RF-04 e RF-56), todos com ``Fonte.MOVIMENTACAO``.

- ``saida_do_leito`` (ALTA): quadril no leito por ≥ 3 s e depois fora por ≥ 3 s.
- ``imobilidade_prolongada`` (ALTA): velocidade abaixo do limiar por ≥ ``imobilidade_s``.
- ``movimentacao_atipica`` (INFO): janela com movimento muito acima do padrão do próprio vídeo
  (z-score robusto: mediana e MAD das janelas anteriores, que um pico isolado não distorce).

O ``instante`` de cada evento é o começo do fato (quando saiu, quando parou,
começo da janela agitada); o ``valor`` é a medida que disparou.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from monitor.eventos import Evento, Fonte, Severidade
from monitor.movimentacao.config import ConfigMovimentacao
from monitor.movimentacao.serie import calcular
from monitor.video.geometria import mediana_movel
from monitor.video.quarto import EstadoQuadro

DETECTOR = "movimentacao/v1"


def _evento(paciente_id: str, inicio: datetime, t_s: float, tipo: str, severidade: Severidade,
            descricao: str, valor: float) -> Evento:
    return Evento(paciente_id, inicio + timedelta(seconds=t_s), Fonte.MOVIMENTACAO, tipo, severidade,
                  descricao, DETECTOR, round(float(valor), 3))


def detectar_saida_do_leito(
    estados: Sequence[EstadoQuadro], paciente_id: str, inicio: datetime,
    cfg: ConfigMovimentacao = ConfigMovimentacao(),
) -> list[Evento]:
    """Só muda de situação (no leito ↔ fora) quando a nova situação dura o tempo mínimo.

    Ausente conta como fora: quem sai do leito e da imagem saiu do leito.
    """
    eventos: list[Evento] = []
    confirmado: bool | None = None  # situação aceita: True no leito, False fora
    candidato: bool | None = None
    desde = 0.0
    for e in estados:
        if e.no_leito is None:  # sem zona do leito não há como saber
            return []
        if e.no_leito != candidato:
            candidato, desde = e.no_leito, e.t_s
        minimo = cfg.saida_dentro_s if candidato else cfg.saida_fora_s
        if candidato != confirmado and e.t_s - desde >= minimo:
            if confirmado is True and candidato is False:
                eventos.append(_evento(paciente_id, inicio, desde, "saida_do_leito", Severidade.ALTA,
                                       f"Paciente saiu do leito e ficou fora por pelo menos {minimo:.0f} s.",
                                       e.t_s - desde))
            confirmado = candidato
    return eventos


def detectar_imobilidade(
    estados: Sequence[EstadoQuadro], paciente_id: str, inicio: datetime,
    cfg: ConfigMovimentacao = ConfigMovimentacao(),
) -> list[Evento]:
    """Um evento por trecho parado de pelo menos ``imobilidade_s``; valor = duração do trecho.

    Velocidade suavizada por mediana móvel, para o tremor do esqueleto não contar como movimento.
    Ausência do paciente interrompe o trecho.
    """
    velocidade = mediana_movel([e.movimento for e in estados], cfg.mediana_quadros)
    eventos: list[Evento] = []
    comeco: float | None = None
    ultimo_parado = 0.0
    for e, v in list(zip(estados, velocidade)) + [(None, np.nan)]:  # None fecha o último trecho
        parado = e is not None and e.presente and not v >= cfg.imobilidade_limiar  # NaN não interrompe
        if parado:
            comeco = e.t_s if comeco is None else comeco
            ultimo_parado = e.t_s
            continue
        if comeco is not None and ultimo_parado - comeco >= cfg.imobilidade_s:
            duracao = ultimo_parado - comeco
            eventos.append(_evento(paciente_id, inicio, comeco, "imobilidade_prolongada", Severidade.ALTA,
                                   f"Paciente sem se mexer por {duracao:.0f} s (limite {cfg.imobilidade_s:.0f} s).",
                                   duracao))
        comeco = None
    return eventos


def detectar_agitacao(
    serie: pd.DataFrame, paciente_id: str, inicio: datetime,
    cfg: ConfigMovimentacao = ConfigMovimentacao(),
) -> list[Evento]:
    """z = (movimento - mediana) / (1,4826 × MAD) contra as janelas válidas anteriores.

    1,4826 × MAD estima o desvio padrão numa distribuição normal. Só o lado
    positivo conta (agitação); movimento muito abaixo do padrão é imobilidade.
    """
    eventos: list[Evento] = []
    historico: list[float] = []
    for linha in serie.itertuples():
        if np.isnan(linha.movimento) or linha.presente < cfg.presenca_min:
            continue
        if len(historico) >= cfg.min_janelas:
            mediana = float(np.median(historico))
            mad = float(np.median(np.abs(np.array(historico) - mediana)))
            z = (linha.movimento - mediana) / max(1.4826 * mad, cfg.mad_minimo)
            if z > cfg.z_limiar:
                eventos.append(_evento(paciente_id, inicio, linha.inicio_s, "movimentacao_atipica", Severidade.INFO,
                                       f"Movimentação {z:.1f} desvios acima do padrão da sessão (agitação) "
                                       f"entre {linha.inicio_s:.0f} s e {linha.fim_s:.0f} s.", z))
        historico.append(float(linha.movimento))
    return eventos


def detectar(
    estados: Sequence[EstadoQuadro], paciente_id: str, inicio: datetime,
    cfg: ConfigMovimentacao = ConfigMovimentacao(),
) -> list[Evento]:
    eventos = (detectar_saida_do_leito(estados, paciente_id, inicio, cfg)
               + detectar_imobilidade(estados, paciente_id, inicio, cfg)
               + detectar_agitacao(calcular(estados, cfg.janela_s), paciente_id, inicio, cfg))
    return sorted(eventos, key=lambda e: e.instante)
