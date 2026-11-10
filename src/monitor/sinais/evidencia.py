"""Arquivos de evidência dos sinais vitais: trecho ao redor de cada evento e série inteira."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from monitor.config import CAMINHOS
from monitor.eventos import Evento
from monitor.sinais.config import CONFIG


def com_instante(df: pd.DataFrame, inicio: datetime) -> pd.DataFrame:
    saida = df.copy()
    saida.insert(1, "instante", [(inicio + pd.Timedelta(seconds=float(s))).isoformat() for s in saida["t_s"]])
    return saida


def gravar_evidencia(df: pd.DataFrame, evento: Evento, inicio: datetime) -> None:
    """CSV com os 120 s ao redor do evento, no caminho que a evidência já aponta."""
    t = (evento.instante - inicio).total_seconds()
    meia = CONFIG.meia_janela_evidencia_s
    trecho = df[(df["t_s"] >= t - meia) & (df["t_s"] <= t + meia)]
    caminho = CAMINHOS.raiz / evento.evidencia["serie"]
    caminho.parent.mkdir(parents=True, exist_ok=True)
    com_instante(trecho, inicio).to_csv(caminho, index=False)


def gravar_serie(df: pd.DataFrame, inicio: datetime, caminho: Path) -> Path:
    """Série inteira reproduzida (com as anomalias plantadas, se houver), para o painel."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    com_instante(df, inicio).to_csv(caminho, index=False)
    return caminho
