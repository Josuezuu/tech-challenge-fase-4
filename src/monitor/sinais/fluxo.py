"""Reprodução de uma série 1 Hz como fluxo, amostra a amostra (RF-41)."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterator

import pandas as pd

VARIAVEIS = ("fc", "pulso", "fr", "spo2", "pas")


@dataclass(frozen=True)
class Amostra:
    paciente_id: str
    instante: datetime
    valores: dict[str, float]  # NaN = buraco na série
    t_s: float = 0.0  # segundos desde o início da gravação (para a evidência)


def reproduzir(
    df: pd.DataFrame,
    paciente_id: str,
    inicio: datetime,
    velocidade: float | None = None,
) -> Iterator[Amostra]:
    """Gera uma ``Amostra`` por linha, na ordem de ``t_s``.

    ``instante = inicio + t_s``. ``velocidade=None`` (ou 0) não dorme: serve
    para avaliação. ``velocidade=60`` dorme 1/60 s por amostra (1 min de
    gravação em 1 s), para a demonstração parecer um monitor de verdade.
    """
    colunas = [c for c in VARIAVEIS if c in df.columns]
    for linha in df.sort_values("t_s").itertuples(index=False):
        t_s = float(getattr(linha, "t_s"))
        valores = {c: float(getattr(linha, c)) for c in colunas}
        yield Amostra(paciente_id=paciente_id, instante=inicio + timedelta(seconds=t_s), valores=valores, t_s=t_s)
        if velocidade:
            time.sleep(1.0 / velocidade)


def valido(valor: float | None) -> bool:
    return valor is not None and not math.isnan(valor)
