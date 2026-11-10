"""Conversão de qualquer áudio/vídeo para WAV PCM 16 bits, mono, 16 kHz (RF-30).

Usa o ffmpeg empacotado no ``imageio-ffmpeg`` (sem instalação no sistema).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import imageio_ffmpeg

from monitor.audio.config import CONFIG, ConfigAudio
from monitor.config import CAMINHOS

DIR_SAIDA = CAMINHOS.resultados / "audio"


def para_wav(entrada: Path, saida: Path | None = None, cfg: ConfigAudio = CONFIG) -> Path:
    """Converte ``entrada`` (m4a, mp3, mp4, ogg, wav...) para WAV mono 16 kHz.

    Saída padrão: ``results/audio/<nome>.wav``. O roteiro ``<entrada>.txt``,
    se existir, é copiado para junto do WAV (a transcrição simulada o lê).
    """
    entrada = Path(entrada)
    if not entrada.exists():
        raise FileNotFoundError(entrada)
    saida = Path(saida) if saida else DIR_SAIDA / f"{entrada.stem}.wav"
    if saida.resolve() == entrada.resolve():
        raise ValueError(f"a saída não pode ser o próprio arquivo de entrada: {entrada}")
    saida.parent.mkdir(parents=True, exist_ok=True)

    comando = [
        imageio_ffmpeg.get_ffmpeg_exe(),
        "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(entrada),
        "-vn",  # ignora a trilha de vídeo de um mp4
        "-ac", "1",
        "-ar", str(cfg.taxa_amostragem_hz),
        "-c:a", "pcm_s16le",
        str(saida),
    ]
    resultado = subprocess.run(comando, capture_output=True, text=True)
    if resultado.returncode != 0:
        raise RuntimeError(f"ffmpeg falhou ao converter {entrada}: {resultado.stderr.strip()}")

    roteiro = entrada.with_suffix(".txt")
    if roteiro.exists():
        shutil.copyfile(roteiro, saida.with_suffix(".txt"))
    return saida
