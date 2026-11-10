"""Geometria do esqueleto: ângulos, centro do quadril, inclinação do tronco, tamanho do corpo.

Coordenadas de imagem: x para a direita, **y para baixo**. Todas as funções
devolvem NaN quando falta algum ponto, em vez de inventar valor.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from monitor.video.config import OMBRO_D, OMBRO_E, QUADRIL_D, QUADRIL_E
from monitor.video.tipos import Caixa

NAN_2 = np.array([np.nan, np.nan])


def angulo(a: np.ndarray, vertice: np.ndarray, c: np.ndarray) -> float:
    """Ângulo em graus no ``vertice`` entre os segmentos vértice→a e vértice→c (0 a 180)."""
    u = np.asarray(a, dtype=float) - np.asarray(vertice, dtype=float)
    v = np.asarray(c, dtype=float) - np.asarray(vertice, dtype=float)
    nu, nv = np.linalg.norm(u), np.linalg.norm(v)
    if not (nu > 0 and nv > 0):  # NaN ou segmento de comprimento zero
        return float("nan")
    cosseno = np.clip(np.dot(u, v) / (nu * nv), -1.0, 1.0)
    return float(np.degrees(np.arccos(cosseno)))


def _media_par(pontos: np.ndarray, i: int, j: int) -> np.ndarray:
    par = pontos[[i, j]]
    validos = par[~np.isnan(par).any(axis=1)]
    return validos.mean(axis=0) if len(validos) else NAN_2.copy()


def centro_quadril(pontos: np.ndarray) -> np.ndarray:
    """Média dos dois quadris; se só um aparece, ele mesmo."""
    return _media_par(pontos, QUADRIL_E, QUADRIL_D)


def centro_ombros(pontos: np.ndarray) -> np.ndarray:
    return _media_par(pontos, OMBRO_E, OMBRO_D)


def inclinacao_tronco(pontos: np.ndarray) -> float:
    """Ângulo em graus entre o tronco (quadril→ombros) e a vertical: 0 em pé, 90 deitado."""
    q, o = centro_quadril(pontos), centro_ombros(pontos)
    dx, dy = o - q
    if np.isnan(dx) or np.isnan(dy) or (dx == 0 and dy == 0):
        return float("nan")
    return float(np.degrees(np.arctan2(abs(dx), -dy)))  # -dy: "para cima" na imagem


def tamanho_corpo(caixa: Caixa) -> float:
    """Maior lado da caixa: a altura de quem está em pé e o comprimento de quem está deitado.

    Não depende da orientação, então serve de régua antes e depois de uma queda.
    """
    x1, y1, x2, y2 = caixa
    return float(max(x2 - x1, y2 - y1))


def centro_caixa(caixa: Caixa) -> np.ndarray:
    x1, y1, x2, y2 = caixa
    return np.array([(x1 + x2) / 2, (y1 + y2) / 2])


def deslocamento_medio(anterior: np.ndarray, atual: np.ndarray, escala: float) -> float:
    """Deslocamento médio dos pontos visíveis nos dois quadros, em unidades de ``escala``."""
    dist = np.linalg.norm(atual - anterior, axis=1)
    dist = dist[~np.isnan(dist)]
    if len(dist) == 0 or not escala > 0:
        return float("nan")
    return float(dist.mean() / escala)


def mediana_movel(valores: Sequence[float], janela: int) -> np.ndarray:
    """Mediana centrada de ``janela`` amostras, ignorando NaN (NaN só se a janela toda for NaN)."""
    v = np.asarray(valores, dtype=float)
    if janela <= 1 or len(v) == 0:
        return v.copy()
    meio = janela // 2
    saida = np.full(len(v), np.nan)
    for i in range(len(v)):
        trecho = v[max(0, i - meio): i + meio + 1]
        trecho = trecho[~np.isnan(trecho)]
        if len(trecho):
            saida[i] = np.median(trecho)
    return saida


def ampliar_caixa(caixa: Caixa, fracao: float) -> Caixa:
    """Aumenta largura e altura em ``fracao`` (0.10 = 10%) mantendo o centro."""
    x1, y1, x2, y2 = caixa
    dx, dy = (x2 - x1) * fracao / 2, (y2 - y1) * fracao / 2
    return (x1 - dx, y1 - dy, x2 + dx, y2 + dy)


def ponto_no_poligono(ponto: np.ndarray, poligono: Sequence[tuple[float, float]]) -> bool:
    """Teste do raio (ray casting): conta quantas arestas um raio horizontal cruza."""
    x, y = float(ponto[0]), float(ponto[1])
    if np.isnan(x) or np.isnan(y):
        return False
    dentro = False
    n = len(poligono)
    for i in range(n):
        x1, y1 = poligono[i]
        x2, y2 = poligono[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            x_cruzamento = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < x_cruzamento:
                dentro = not dentro
    return dentro
