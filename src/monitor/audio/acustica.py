"""Atributos acústicos da voz por janela de 5 s com fala (RF-34).

Ritmo (pela energia e pelos horários das palavras):

- ``taxa_fala_ppm``: palavras da transcrição cujo meio cai na janela, por minuto de fala;
- ``proporcao_pausa``: fração da janela em pausa;
- ``pausas_por_min``: pausas que começam na janela, por minuto de janela.

VAD por energia: quadros de 25 ms; silêncio = energia abaixo do percentil 20
da gravação + 10 dB; pausa = silêncio contínuo de pelo menos 250 ms (silêncio
mais curto é articulação). O silêncio antes da primeira e depois da última
fala fica fora das janelas.

Qualidade da voz (Praat, via ``parselmouth``): ``f0_media_hz``, ``f0_dp_hz``
(``to_pitch``, 75–500 Hz, só quadros vozeados), ``energia_db`` (dBFS dos
quadros de fala), ``jitter_local``, ``shimmer_local`` (fração) e ``hnr_db``.

``extrair_de_sinal`` é pura (recebe o array); ``extrair`` só lê o WAV e a chama.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import parselmouth
import soundfile as sf
from parselmouth.praat import call

from monitor.audio.config import ATRIBUTOS, CONFIG, ConfigAudio
from monitor.nuvem.azure_fala import Palavra, Transcricao


@dataclass(frozen=True)
class JanelaVoz:
    inicio_s: float
    fim_s: float
    valores: dict[str, float]  # atributo -> valor (nan quando o Praat não consegue medir)


@dataclass(frozen=True)
class AtributosVoz:
    duracao_s: float
    janelas: tuple[JanelaVoz, ...]

    def serie(self, atributo: str) -> np.ndarray:
        return np.array([j.valores[atributo] for j in self.janelas], dtype=float)

    def media(self) -> dict[str, float]:
        return {a: _media_sem_nan(self.serie(a)) for a in ATRIBUTOS}

    def to_dict(self) -> dict[str, Any]:
        return {
            "duracao_s": round(self.duracao_s, 3),
            "media": {a: _para_json(v) for a, v in self.media().items()},
            "janelas": [
                {"inicio_s": j.inicio_s, "fim_s": j.fim_s, **{a: _para_json(v) for a, v in j.valores.items()}}
                for j in self.janelas
            ],
        }


def _media_sem_nan(valores: np.ndarray) -> float:
    validos = valores[~np.isnan(valores)]
    return float(validos.mean()) if len(validos) else math.nan


def _para_json(valor: float) -> float | None:
    return None if math.isnan(valor) else round(float(valor), 4)


# --- VAD por energia -------------------------------------------------------


def energia_por_quadro(sinal: np.ndarray, taxa_hz: int, cfg: ConfigAudio = CONFIG) -> np.ndarray:
    """Energia (dBFS) de cada quadro de ``cfg.quadro_s`` sem sobreposição."""
    tam = int(round(cfg.quadro_s * taxa_hz))
    n = len(sinal) // tam
    quadros = sinal[: n * tam].reshape(n, tam)
    return 10 * np.log10(np.mean(quadros**2, axis=1) + cfg.piso_energia)


def marcar_pausas(energia_db: np.ndarray, cfg: ConfigAudio = CONFIG) -> np.ndarray:
    """``True`` nos quadros que fazem parte de uma pausa (silêncio ≥ ``pausa_minima_s``)."""
    limiar = np.percentile(energia_db, cfg.percentil_ruido) + cfg.margem_vad_db
    silencio = energia_db < limiar
    minimo = int(round(cfg.pausa_minima_s / cfg.quadro_s))
    pausa = np.zeros(len(silencio), dtype=bool)
    i = 0
    while i < len(silencio):
        if not silencio[i]:
            i += 1
            continue
        fim = i
        while fim < len(silencio) and silencio[fim]:
            fim += 1
        if fim - i >= minimo:
            pausa[i:fim] = True
        i = fim
    return pausa


# --- Praat -----------------------------------------------------------------


def _praat_ou_nan(funcao: Any) -> float:
    """O Praat lança erro quando não há períodos vozeados suficientes."""
    try:
        return float(funcao())
    except parselmouth.PraatError:
        return math.nan


def _qualidade_vocal(som: parselmouth.Sound, inicio_s: float, fim_s: float, cfg: ConfigAudio) -> dict[str, float]:
    parte = som.extract_part(from_time=inicio_s, to_time=fim_s, preserve_times=True)
    pulsos = call(parte, "To PointProcess (periodic, cc)", cfg.f0_min_hz, cfg.f0_max_hz)
    periodos = (0, 0, cfg.jitter_periodo_min_s, cfg.jitter_periodo_max_s, cfg.jitter_fator_max)
    return {
        "jitter_local": _praat_ou_nan(lambda: call(pulsos, "Get jitter (local)", *periodos)),
        "shimmer_local": _praat_ou_nan(
            lambda: call([parte, pulsos], "Get shimmer (local)", *periodos, cfg.shimmer_fator_amplitude_max)),
        "hnr_db": _praat_ou_nan(lambda: call(parte.to_harmonicity_cc(), "Get mean", 0, 0)),  # ignora quadros mudos
    }


# --- Janelas ---------------------------------------------------------------


def _limites_das_janelas(inicio_s: float, fim_s: float, cfg: ConfigAudio) -> list[tuple[float, float]]:
    limites = []
    a = inicio_s
    while a < fim_s:
        b = min(a + cfg.janela_s, fim_s)
        if b - a >= cfg.janela_minima_s or not limites:  # a única janela fica, mesmo curta
            limites.append((a, b))
        a += cfg.janela_s
    return limites


def extrair_de_sinal(
    sinal: np.ndarray, taxa_hz: int, palavras: Sequence[Palavra], cfg: ConfigAudio = CONFIG
) -> AtributosVoz:
    """Atributos de cada janela de ``cfg.janela_s`` com pelo menos ``fala_minima_s`` de fala."""
    sinal = np.asarray(sinal, dtype=float)
    duracao = len(sinal) / taxa_hz
    q = cfg.quadro_s
    energia = energia_por_quadro(sinal, taxa_hz, cfg)
    pausa = marcar_pausas(energia, cfg)
    comeca_pausa = pausa & ~np.concatenate(([False], pausa[:-1]))  # primeiro quadro de cada pausa
    falando = np.flatnonzero(~pausa)
    if len(falando) == 0:
        return AtributosVoz(duracao, ())

    som = parselmouth.Sound(sinal, sampling_frequency=taxa_hz)
    pitch = som.to_pitch(pitch_floor=cfg.f0_min_hz, pitch_ceiling=cfg.f0_max_hz)
    tempos_f0 = pitch.xs()
    f0 = pitch.selected_array["frequency"]  # 0 = quadro não vozeado

    janelas = []
    for a, b in _limites_das_janelas(falando[0] * q, (falando[-1] + 1) * q, cfg):
        ia, ib = int(round(a / q)), int(round(b / q))
        em_pausa = pausa[ia:ib]
        fala_s = float(np.sum(~em_pausa)) * q
        if fala_s < cfg.fala_minima_s:
            continue
        n_palavras = sum(1 for p in palavras if a <= (p.inicio_s + p.fim_s) / 2 < b)
        vozeado = f0[(tempos_f0 >= a) & (tempos_f0 < b) & (f0 > 0)]
        potencia_fala = 10 ** (energia[ia:ib][~em_pausa] / 10)
        valores = {
            "taxa_fala_ppm": n_palavras / (fala_s / 60),
            "proporcao_pausa": float(np.mean(em_pausa)),
            "pausas_por_min": float(np.sum(comeca_pausa[ia:ib])) / ((b - a) / 60),
            "f0_media_hz": float(vozeado.mean()) if len(vozeado) >= 2 else math.nan,
            "f0_dp_hz": float(vozeado.std()) if len(vozeado) >= 2 else math.nan,
            "energia_db": float(10 * np.log10(potencia_fala.mean())),
            **_qualidade_vocal(som, a, b, cfg),
        }
        janelas.append(JanelaVoz(round(a, 3), round(b, 3), valores))
    return AtributosVoz(duracao, tuple(janelas))


def extrair(wav: Path, transcricao: Transcricao, cfg: ConfigAudio = CONFIG) -> AtributosVoz:
    """Lê o WAV (mono; se vier estéreo, faz a média dos canais) e extrai os atributos."""
    sinal, taxa = sf.read(str(wav), dtype="float64", always_2d=True)
    return extrair_de_sinal(sinal.mean(axis=1), taxa, transcricao.palavras, cfg)
