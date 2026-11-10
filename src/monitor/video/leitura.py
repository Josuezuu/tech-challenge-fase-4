"""Leitura de vídeo gravado, amostrada a ``fps_alvo`` quadros por segundo (RF-01)."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass(frozen=True)
class Metadados:
    fps: float
    largura: int
    altura: int
    total_quadros: int

    @property
    def duracao_s(self) -> float:
        return self.total_quadros / self.fps if self.fps else 0.0


def _abrir(caminho: Path) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(str(caminho))
    if not cap.isOpened():
        raise FileNotFoundError(f"Não consegui abrir o vídeo {caminho}")
    return cap


def ler_metadados(caminho: Path) -> Metadados:
    cap = _abrir(caminho)
    try:
        return Metadados(
            fps=float(cap.get(cv2.CAP_PROP_FPS)) or 30.0,  # alguns arquivos não informam; 30 é o comum
            largura=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            altura=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            total_quadros=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
        )
    finally:
        cap.release()


def iterar_quadros(caminho: Path, fps_alvo: float) -> Iterator[tuple[float, np.ndarray]]:
    """Devolve ``(t_s, imagem BGR)`` a cada 1/fps_alvo segundo de vídeo.

    Os quadros pulados só são avançados (``grab``), sem decodificar a imagem.
    """
    cap = _abrir(caminho)
    fps = float(cap.get(cv2.CAP_PROP_FPS)) or 30.0
    passo = 1.0 / fps_alvo
    proximo = 0.0
    indice = 0
    try:
        while cap.grab():
            t = indice / fps
            if t + 1e-6 >= proximo:
                ok, imagem = cap.retrieve()
                if not ok:
                    break
                yield round(t, 4), imagem
                proximo += passo
            indice += 1
    finally:
        cap.release()
