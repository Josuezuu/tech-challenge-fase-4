"""Série de movimentação por janela de tempo (RF-07 / RF-55).

Cada linha resume ``janela_s`` segundos do vídeo:

- ``movimento``: velocidade média dos pontos do esqueleto, em tamanhos de corpo por segundo
  (normalizar pelo corpo faz a medida valer para pessoa perto ou longe da câmera);
- ``no_leito``: fração do tempo com o quadril na zona do leito (NaN sem zona);
- ``presente``: fração do tempo com o paciente no quadro.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from monitor.video.quarto import EstadoQuadro

COLUNAS = ["inicio_s", "fim_s", "movimento", "no_leito", "presente"]


def calcular(estados: Sequence[EstadoQuadro], janela_s: float = 10.0) -> pd.DataFrame:
    if not estados:
        return pd.DataFrame(columns=COLUNAS)
    t = np.array([e.t_s for e in estados])
    indice = np.floor(t / janela_s).astype(int)
    linhas = []
    for k in range(int(indice.max()) + 1):
        trecho = [e for e, i in zip(estados, indice) if i == k]
        if not trecho:
            continue
        movimentos = np.array([e.movimento for e in trecho], dtype=float)
        no_leito = [e.no_leito for e in trecho]
        linhas.append({
            "inicio_s": k * janela_s,
            "fim_s": (k + 1) * janela_s,
            "movimento": float(np.nanmean(movimentos)) if not np.isnan(movimentos).all() else np.nan,
            "no_leito": np.nan if None in no_leito else float(np.mean(no_leito)),
            "presente": float(np.mean([e.presente for e in trecho])),
        })
    return pd.DataFrame(linhas, columns=COLUNAS)
