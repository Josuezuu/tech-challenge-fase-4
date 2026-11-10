"""Anomalias plantadas em séries reais, com rótulo (RF-45), e PA sintética (RF-47).

O BIDMC não tem rótulo de evento clínico; para medir recall e atraso,
plantamos anomalias conhecidas sobre as séries reais. A anomalia soma um
deslocamento ao sinal original, então o ruído natural do paciente continua lá.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

from monitor.config import SEMENTE
from monitor.sinais.config import INJECAO, ConfigInjecao

TIPOS: dict[str, str] = {  # tipo de anomalia → variável afetada
    "queda_spo2": "spo2",
    "taquicardia": "fc",
    "bradicardia": "fc",
    "taquipneia": "fr",
    "degrau_fc": "fc",
}


@dataclass(frozen=True)
class Especificacao:
    tipo: str
    inicio_s: float
    duracao_s: float


@dataclass(frozen=True)
class Rotulo:
    inicio_s: float
    fim_s: float
    tipo: str
    variavel: str
    alvo: float  # valor de pico (queda/brady/taquipneia) ou deslocamento somado (taqui/degrau)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _perfil(t: np.ndarray, inicio: float, fim: float, rampa: float) -> np.ndarray:
    """Fator 0..1 da anomalia ao longo do tempo: sobe em ``rampa`` s, fica em 1, desce em ``rampa`` s."""
    f = np.zeros_like(t, dtype=float)
    dentro = (t >= inicio) & (t <= fim)
    if rampa <= 0:
        f[dentro] = 1.0
        return f
    subida = (t[dentro] - inicio) / rampa
    descida = (fim - t[dentro]) / rampa
    f[dentro] = np.clip(np.minimum(subida, descida), 0.0, 1.0)
    return f


def plantar(
    df: pd.DataFrame,
    especificacoes: list[Especificacao],
    semente: int = SEMENTE,
    config: ConfigInjecao = INJECAO,
) -> tuple[pd.DataFrame, list[Rotulo]]:
    """Devolve uma cópia de ``df`` com as anomalias e os rótulos. O original fica intocado."""
    rng = np.random.default_rng(semente)
    saida = df.copy()
    t = saida["t_s"].to_numpy(dtype=float)
    rotulos: list[Rotulo] = []
    for esp in especificacoes:
        if esp.tipo not in TIPOS:
            raise ValueError(f"tipo de anomalia desconhecido: {esp.tipo!r} (use {sorted(TIPOS)})")
        variavel = TIPOS[esp.tipo]
        fim = esp.inicio_s + esp.duracao_s
        serie = saida[variavel].to_numpy(dtype=float)
        base = float(np.nanmedian(serie))
        if esp.tipo == "queda_spo2":
            alvo = float(rng.uniform(*config.spo2_alvo))
            deslocamento = min(alvo - base, -config.queda_minima_spo2)
            rampa = esp.duracao_s / 3  # rampa até o alvo, platô, volta
        elif esp.tipo == "taquicardia":
            alvo = float(rng.uniform(*config.taquicardia_delta))
            deslocamento, rampa = alvo, config.rampa_s
        elif esp.tipo == "bradicardia":
            alvo = float(rng.uniform(*config.bradicardia_alvo))
            deslocamento, rampa = alvo - base, config.rampa_s
        elif esp.tipo == "taquipneia":
            alvo = float(rng.uniform(*config.taquipneia_alvo))
            deslocamento, rampa = alvo - base, config.rampa_s
        else:  # degrau_fc
            alvo = float(rng.uniform(*config.degrau_fc_delta))
            deslocamento, rampa = alvo, 0.0
        nova = serie + _perfil(t, esp.inicio_s, fim, rampa) * deslocamento
        if variavel == "spo2":
            nova = np.minimum(nova, 100.0)
        saida[variavel] = np.round(nova)  # o monitor entrega inteiros
        rotulos.append(Rotulo(esp.inicio_s, fim, esp.tipo, variavel, round(alvo, 1)))
    return saida, rotulos


def sortear(
    df: pd.DataFrame,
    n: int,
    semente: int = SEMENTE,
    config: ConfigInjecao = INJECAO,
) -> list[Especificacao]:
    """Sorteia ``n`` anomalias (tipo, início, duração) sem sobreposição, separadas por ``intervalo_minimo_s``."""
    rng = np.random.default_rng(semente)
    t_fim = float(df["t_s"].max())
    escolhidas: list[Especificacao] = []
    for _ in range(1000):
        if len(escolhidas) == n:
            break
        duracao = int(rng.integers(config.duracao_min_s, config.duracao_max_s + 1))
        ultimo_inicio = t_fim - duracao
        if ultimo_inicio <= config.margem_inicio_s:
            continue
        inicio = int(rng.integers(config.margem_inicio_s, int(ultimo_inicio) + 1))
        folga = config.intervalo_minimo_s
        if any(inicio < e.inicio_s + e.duracao_s + folga and e.inicio_s < inicio + duracao + folga
               for e in escolhidas):
            continue
        escolhidas.append(Especificacao(str(rng.choice(list(TIPOS))), inicio, duracao))
    if len(escolhidas) < n:
        raise ValueError(f"não coube {n} anomalias sem sobreposição em {t_fim:g} s")
    return sorted(escolhidas, key=lambda e: e.inicio_s)


def plantar_aleatorio(
    df: pd.DataFrame,
    n: int,
    semente: int = SEMENTE,
    config: ConfigInjecao = INJECAO,
) -> tuple[pd.DataFrame, list[Rotulo]]:
    return plantar(df, sortear(df, n, semente, config), semente, config)


def pressao_sintetica(n: int, semente: int = SEMENTE) -> np.ndarray:
    """PA sistólica sintética (mmHg) entre 110 e 130: base + oscilação lenta + ruído (RF-47).

    O BIDMC não tem pressão; esta série só existe para mostrar o limiar de PA
    funcionando, e todo evento dela é marcado como sintético.
    """
    rng = np.random.default_rng(semente)
    t = np.arange(n, dtype=float)
    base = rng.uniform(116, 124)
    oscilacao = 4 * np.sin(2 * np.pi * t / 180 + rng.uniform(0, 2 * np.pi))  # ciclo de 3 min
    ruido = rng.normal(0, 1.5, n)
    return np.round(np.clip(base + oscilacao + ruido, 110, 130))
