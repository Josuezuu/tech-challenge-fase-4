from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from monitor.config import SEMENTE
from monitor.eventos import Evento
from monitor.sinais.detectores import MonitorVitais
from monitor.sinais.fluxo import reproduzir

INICIO = datetime(2026, 11, 12, 14, 0, 0)


def serie(n: int = 481, fc: float = 80, fr: float = 16, spo2: float = 97, ruido: bool = False) -> pd.DataFrame:
    """Série 1 Hz feita à mão; com ``ruido`` soma ±2 em FC, ±1 em FR e 0/-1 em SpO2."""
    rng = np.random.default_rng(SEMENTE)
    df = pd.DataFrame({
        "t_s": np.arange(n, dtype=float),
        "fc": np.full(n, fc, dtype=float),
        "pulso": np.full(n, fc, dtype=float),
        "fr": np.full(n, fr, dtype=float),
        "spo2": np.full(n, spo2, dtype=float),
    })
    if ruido:
        df["fc"] += rng.integers(-2, 3, n)
        df["fr"] += rng.integers(-1, 2, n)
        df["spo2"] += rng.integers(-1, 1, n)
    return df


def rodar(df: pd.DataFrame, monitor: MonitorVitais | None = None) -> list[Evento]:
    monitor = monitor or MonitorVitais(gravacao="teste")
    eventos: list[Evento] = []
    for amostra in reproduzir(df, "leito-12", INICIO):
        eventos.extend(monitor.processar(amostra))
    return eventos
