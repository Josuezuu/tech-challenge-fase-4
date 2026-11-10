"""Leitura das Numerics do BIDMC (1 Hz): ``Time [s], HR, PULSE, RESP, SpO2``."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from monitor.config import CAMINHOS

URL_BIDMC = "https://physionet.org/files/bidmc/1.0.0/bidmc_csv/bidmc_{nr:02d}_Numerics.csv"
DIR_BIDMC = CAMINHOS.brutos / "bidmc"

# Cabeçalho real (com espaço depois da vírgula) → nomes limpos usados no projeto.
COLUNAS = {"Time [s]": "t_s", "HR": "fc", "PULSE": "pulso", "RESP": "fr", "SpO2": "spo2"}


def arquivo_bidmc(nr: int, pasta: Path | None = None) -> Path:
    return (pasta or DIR_BIDMC) / f"bidmc_{nr:02d}_Numerics.csv"


def nome_gravacao(nr: int) -> str:
    return f"bidmc_{nr:02d}"


def ler_numerics(caminho: Path) -> pd.DataFrame:
    """Lê um CSV de Numerics e devolve ``t_s, fc, pulso, fr, spo2`` em float.

    Valor vazio ou inválido vira ``NaN`` (o detector pula o buraco); linha sem
    tempo é descartada.
    """
    bruto = pd.read_csv(caminho, skipinitialspace=True)
    bruto.columns = [c.strip() for c in bruto.columns]
    faltando = [c for c in COLUNAS if c not in bruto.columns]
    if faltando:
        raise ValueError(f"{caminho.name}: colunas ausentes {faltando}")
    df = bruto[list(COLUNAS)].rename(columns=COLUNAS)
    df = df.apply(pd.to_numeric, errors="coerce").astype(float)
    df = df.dropna(subset=["t_s"]).sort_values("t_s").reset_index(drop=True)
    return df


def carregar(nr: int, pasta: Path | None = None) -> pd.DataFrame:
    caminho = arquivo_bidmc(nr, pasta)
    if not caminho.exists():
        raise FileNotFoundError(f"{caminho} não existe; rode: python scripts/baixar_bidmc.py")
    return ler_numerics(caminho)
