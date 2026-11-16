"""Voz "cansada" produzida a partir de uma gravação real, para testar a alteração vocal.

Não há gravação de paciente de fato cansado; este módulo aplica a uma voz
humana os sinais que o detector procura (fala mais lenta, mais pausas, voz
mais fraca) em intensidades conhecidas. O resultado é um controle positivo
com gabarito: prova que o detector reage ao padrão, não que acerta em
pacientes reais.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import parselmouth
from parselmouth.praat import call

from monitor.audio.config import CONFIG
from monitor.nuvem.azure_fala import Palavra


@dataclass(frozen=True)
class NivelCansaco:
    lentidao: float  # fator de duração (1,2 = fala 20% mais lenta, mesma altura da voz)
    pausa_a_cada: int  # insere uma pausa a cada N palavras
    pausa_s: float  # duração de cada pausa inserida
    ganho_db: float  # voz mais fraca
    sopro_db: float | None  # ruído de sopro N dB abaixo da fala (None = sem ruído)


NIVEIS: dict[str, NivelCansaco] = {
    "leve": NivelCansaco(1.10, 8, 0.40, -3.0, None),
    "moderada": NivelCansaco(1.20, 5, 0.60, -6.0, None),
    "forte": NivelCansaco(1.35, 3, 0.80, -9.0, 22.0),
}


def cansar(
    sinal: np.ndarray, taxa_hz: int, palavras: tuple[Palavra, ...], nivel: str, semente: int = 0
) -> tuple[np.ndarray, tuple[Palavra, ...]]:
    """Devolve o sinal alterado e as palavras com os tempos novos."""
    n = NIVEIS[nivel]
    som = parselmouth.Sound(np.asarray(sinal, dtype=float), sampling_frequency=taxa_hz)
    som = call(som, "Lengthen (overlap-add)", CONFIG.f0_min_hz, CONFIG.f0_max_hz, n.lentidao)
    x = som.values[0].copy()
    esticadas = [Palavra(p.texto, p.inicio_s * n.lentidao, p.fim_s * n.lentidao, p.confianca) for p in palavras]

    pedacos, novas, cursor, desloc = [], [], 0, 0.0
    for i, p in enumerate(esticadas):
        novas.append(Palavra(p.texto, p.inicio_s + desloc, p.fim_s + desloc, p.confianca))
        if (i + 1) % n.pausa_a_cada == 0 and i + 1 < len(esticadas):
            corte = int(round((p.fim_s + esticadas[i + 1].inicio_s) / 2 * taxa_hz))  # entre duas palavras
            pedacos += [x[cursor:corte], np.zeros(int(round(n.pausa_s * taxa_hz)))]
            cursor, desloc = corte, desloc + n.pausa_s
    pedacos.append(x[cursor:])
    y = np.concatenate(pedacos) * 10 ** (n.ganho_db / 20)

    if n.sopro_db is not None:  # ruído só onde há fala (voz soprosa)
        envelope = np.convolve(np.abs(y), np.ones(400) / 400, mode="same")
        fala = envelope > envelope.max() * 0.05
        rms = float(np.sqrt(np.mean(y[fala] ** 2)))
        y = y + np.random.default_rng(semente).normal(0, rms * 10 ** (-n.sopro_db / 20), len(y)) * fala
    return np.clip(y, -1.0, 1.0), tuple(novas)
