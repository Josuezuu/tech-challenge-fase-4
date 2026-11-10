"""Vídeo anotado e recortes de quadro como evidência dos eventos (RF-05).

Uma passada pelo vídeo, na mesma amostragem da inferência: desenha zona do
leito, objetos, esqueletos (paciente em verde), o rótulo de estado do quadro
e, por 3 s depois de cada evento, uma faixa vermelha com o tipo. O primeiro
quadro de cada evento também vira um ``.jpg``.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from pathlib import Path

import cv2
import numpy as np

from monitor.video.leitura import iterar_quadros
from monitor.video.tipos import Pessoa, Poligono, QuadroAnalisado

LIGACOES = [(0, 1), (0, 2), (1, 3), (2, 4), (5, 6), (5, 7), (7, 9), (6, 8), (8, 10), (5, 11), (6, 12),
            (11, 12), (11, 13), (13, 15), (12, 14), (14, 16)]
VERDE, CINZA, AMARELO, VERMELHO, BRANCO = (60, 200, 60), (160, 160, 160), (0, 220, 255), (40, 40, 230), (255, 255, 255)
EVENTO_NA_TELA_S = 3.0

Marca = tuple[float, str]  # (t_s do evento, texto curto)


def _ascii(texto: str) -> str:
    """As fontes do OpenCV não têm acento: "saída" vira "saida"."""
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()


def _escrever(imagem: np.ndarray, texto: str, origem: tuple[int, int], cor: tuple[int, int, int],
              fundo: tuple[int, int, int] = (0, 0, 0)) -> None:
    texto = _ascii(texto)
    (w, h), base = cv2.getTextSize(texto, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
    x, y = origem
    cv2.rectangle(imagem, (x - 2, y - h - 4), (x + w + 2, y + base), fundo, -1)
    cv2.putText(imagem, texto, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, cor, 2, cv2.LINE_AA)


def _esqueleto(imagem: np.ndarray, pessoa: Pessoa, cor: tuple[int, int, int]) -> None:
    p = pessoa.pontos
    for a, b in LIGACOES:
        if not (np.isnan(p[a]).any() or np.isnan(p[b]).any()):
            cv2.line(imagem, tuple(int(v) for v in p[a]), tuple(int(v) for v in p[b]), cor, 2, cv2.LINE_AA)
    for ponto in p:
        if not np.isnan(ponto).any():
            cv2.circle(imagem, tuple(int(v) for v in ponto), 3, cor, -1)
    x1, y1, x2, y2 = (int(v) for v in pessoa.caixa)
    cv2.rectangle(imagem, (x1, y1), (x2, y2), cor, 1)


def desenhar(imagem: np.ndarray, quadro: QuadroAnalisado, paciente: Pessoa | None, zona: Poligono | None,
             rotulo: str, avisos: Sequence[str]) -> np.ndarray:
    saida = imagem.copy()
    if zona is not None:
        cv2.polylines(saida, [np.array(zona, dtype=np.int32)], True, AMARELO, 2)
    for o in quadro.objetos:
        x1, y1, x2, y2 = (int(v) for v in o.caixa)
        cv2.rectangle(saida, (x1, y1), (x2, y2), CINZA, 1)
        _escrever(saida, o.classe, (x1 + 2, y1 + 18), CINZA)
    for pessoa in quadro.pessoas:
        _esqueleto(saida, pessoa, VERDE if pessoa is paciente else CINZA)
    _escrever(saida, f"{quadro.t_s:6.1f}s  {rotulo}", (8, 24), BRANCO)
    for k, aviso in enumerate(avisos):
        _escrever(saida, aviso.upper(), (8, 54 + 30 * k), BRANCO, VERMELHO)
    return saida


def gravar_anotado(
    video: Path,
    fps_alvo: float,
    quadros: Sequence[QuadroAnalisado],
    pacientes: Sequence[Pessoa | None],
    zona: Poligono | None,
    rotulos: Sequence[str],
    marcas: Sequence[Marca],
    destino: Path,
    dir_recortes: Path,
) -> list[Path | None]:
    """Grava ``destino`` (.mp4, codec ``mp4v``, na taxa amostrada) e um ``.jpg`` por marca.

    Devolve o caminho do recorte de cada marca, na ordem de ``marcas`` (None se o vídeo não tinha quadro).
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    dir_recortes.mkdir(parents=True, exist_ok=True)
    recortes: list[Path | None] = [None] * len(marcas)
    escritor: cv2.VideoWriter | None = None
    ultima: np.ndarray | None = None
    try:
        for i, ((t, imagem), quadro) in enumerate(zip(iterar_quadros(video, fps_alvo), quadros)):
            avisos = [texto for t_m, texto in marcas if t_m - 1e-6 <= t < t_m + EVENTO_NA_TELA_S]
            anotada = desenhar(imagem, quadro, pacientes[i], zona, rotulos[i], avisos)
            if escritor is None:
                altura, largura = anotada.shape[:2]
                escritor = cv2.VideoWriter(str(destino), cv2.VideoWriter_fourcc(*"mp4v"), fps_alvo, (largura, altura))
            escritor.write(anotada)
            ultima = anotada
            for k, (t_m, texto) in enumerate(marcas):
                if recortes[k] is None and t >= t_m - 1e-6:
                    recortes[k] = _salvar_recorte(anotada, dir_recortes, k, texto, t_m)
    finally:
        if escritor is not None:
            escritor.release()
    # Marca depois do último quadro lido (arredondamento): usa o último quadro.
    for k, (t_m, texto) in enumerate(marcas):
        if recortes[k] is None and ultima is not None:
            recortes[k] = _salvar_recorte(ultima, dir_recortes, k, texto, t_m)
    return recortes


def _salvar_recorte(imagem: np.ndarray, pasta: Path, k: int, texto: str, t_s: float) -> Path:
    nome = _ascii(texto).replace(" ", "_")
    caminho = pasta / f"{k:02d}_{nome}_{t_s:06.1f}s.jpg"
    cv2.imwrite(str(caminho), imagem)
    return caminho
