"""Alteração vocal: desvio da tomada atual em relação à referência do próprio paciente (RF-34).

Para cada atributo, ``z = (média_atual − média_ref) / desvio_ref``, em que
``desvio_ref`` é o desvio-padrão das janelas da referência, com piso em
``cfg.desvio_minimo`` (referência curta tem desvio quase zero e o z explode).
Um atributo piora quando ``z`` vai na direção de piora dele com ``|z| ≥ 2``;
há alteração quando pelo menos dois atributos pioram.

Não é diagnóstico: o evento diz que a voz se afastou da referência do
paciente, não por quê (cansaço, sedação, dor, emoção, microfone...).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

import numpy as np

from monitor.audio.acustica import AtributosVoz
from monitor.audio.config import ATRIBUTOS, CONFIG, ConfigAudio
from monitor.eventos import Evento, Fonte, Severidade

DETECTOR = "alteracao_vocal/v1"

NOMES = {
    "taxa_fala_ppm": "taxa de fala",
    "proporcao_pausa": "proporção de pausa",
    "pausas_por_min": "pausas por minuto",
    "f0_media_hz": "F0 média",
    "f0_dp_hz": "variação da F0",
    "energia_db": "energia",
    "jitter_local": "jitter",
    "shimmer_local": "shimmer",
    "hnr_db": "HNR",
}


@dataclass(frozen=True)
class ComparacaoAtributo:
    atributo: str
    media_referencia: float
    desvio_referencia: float  # o usado no z, já com o piso
    media_atual: float
    z: float  # nan quando um dos lados não tem medida
    direcao_piora: int  # +1 piora subindo, -1 piora descendo, 0 informativo
    piorou: bool


@dataclass(frozen=True)
class ResultadoVoz:
    atributos: tuple[ComparacaoAtributo, ...]
    janelas_referencia: int
    janelas_atual: int
    alteracao: bool

    @property
    def alterados(self) -> tuple[ComparacaoAtributo, ...]:
        return tuple(a for a in self.atributos if a.piorou)

    def to_dict(self) -> dict[str, Any]:
        def limpo(d: dict[str, Any]) -> dict[str, Any]:
            return {k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in d.items()}

        return {
            "alteracao": self.alteracao,
            "alterados": [a.atributo for a in self.alterados],
            "janelas_referencia": self.janelas_referencia,
            "janelas_atual": self.janelas_atual,
            "atributos": [limpo(asdict(a)) for a in self.atributos],
        }


def comparar(referencia: AtributosVoz, atual: AtributosVoz, cfg: ConfigAudio = CONFIG) -> ResultadoVoz:
    """z-score de cada atributo da tomada atual contra as janelas da referência."""
    comparacoes = []
    medias_atuais = atual.media()
    for atributo in ATRIBUTOS:
        ref = referencia.serie(atributo)
        ref = ref[~np.isnan(ref)]
        media_ref = float(ref.mean()) if len(ref) else math.nan
        desvio = float(ref.std(ddof=1)) if len(ref) >= 2 else 0.0
        desvio = max(desvio, cfg.desvio_minimo[atributo])
        media_atual = medias_atuais[atributo]
        z = (media_atual - media_ref) / desvio
        direcao = cfg.direcao_piora[atributo]
        piorou = not math.isnan(z) and direcao != 0 and direcao * z >= cfg.limiar_z
        comparacoes.append(ComparacaoAtributo(atributo, media_ref, desvio, media_atual, z, direcao, piorou))
    n_piores = sum(c.piorou for c in comparacoes)
    return ResultadoVoz(
        atributos=tuple(comparacoes),
        janelas_referencia=len(referencia.janelas),
        janelas_atual=len(atual.janelas),
        alteracao=n_piores >= cfg.min_atributos_alterados,
    )


def detectar(resultado: ResultadoVoz, paciente_id: str, instante: datetime) -> list[Evento]:
    """Evento ALTA ``alteracao_vocal`` quando a comparação acusa alteração."""
    if not resultado.alteracao:
        return []
    alterados = resultado.alterados
    resumo = "; ".join(
        f"{NOMES[a.atributo]} {'↑' if a.z > 0 else '↓'} (z = {a.z:+.1f})" for a in alterados
    )
    return [Evento(
        paciente_id=paciente_id,
        instante=instante,
        fonte=Fonte.AUDIO,
        tipo="alteracao_vocal",
        severidade=Severidade.ALTA,
        descricao=f"Voz com desvio em relação à voz de referência do paciente em {len(alterados)} "
                  f"atributos: {resumo}. Indica mudança, não diagnóstico.",
        detector=DETECTOR,
        valor=float(len(alterados)),
        evidencia={
            "atributos": ", ".join(a.atributo for a in alterados),
            **{f"z_{a.atributo}": f"{a.z:+.2f}" for a in alterados},
            "janelas_referencia": str(resultado.janelas_referencia),
            "janelas_atual": str(resultado.janelas_atual),
        },
    )]
