"""Gerador de poses sintéticas para testar a lógica sem vídeo nem YOLO.

Uma pessoa é descrita por poucos números (posição do quadril, inclinação do
tronco, ângulo dos braços) e vira os 17 pontos COCO em pixels. Uma cena é uma
lista de trechos ``(duração_s, postura_inicial, postura_final)`` interpolados
linearmente na taxa de quadros pedida.

Imagem de 640×480. Chão em y=450. Leito na caixa (300, 250, 600, 400).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import cv2
import numpy as np

from monitor.config import SEMENTE
from monitor.video.tipos import Caixa, Objeto, Pessoa, QuadroAnalisado

ALTURA = 300.0  # px, pessoa em pé
CHAO = 450.0
LEITO: Caixa = (300.0, 250.0, 600.0, 400.0)
QUADRIL_EM_PE = CHAO - 0.53 * ALTURA  # y do quadril de quem está em pé
QUADRIL_NO_CHAO = CHAO - 0.05 * ALTURA  # y do quadril de quem está deitado no chão
QUADRIL_NA_CAMA = 300.0

# Pontos COCO de quem está em pé: (x relativo ao centro, altura acima do chão), em fração da altura.
MODELO = np.array([
    [0.00, 0.93],                 # 0 nariz
    [-0.02, 0.95], [0.02, 0.95],  # olhos
    [-0.04, 0.94], [0.04, 0.94],  # orelhas
    [-0.10, 0.82], [0.10, 0.82],  # ombros E/D
    [-0.12, 0.65], [0.12, 0.65],  # cotovelos
    [-0.13, 0.50], [0.13, 0.50],  # punhos
    [-0.06, 0.53], [0.06, 0.53],  # quadris
    [-0.06, 0.28], [0.06, 0.28],  # joelhos
    [-0.06, 0.04], [0.06, 0.04],  # tornozelos
])
ALTURA_QUADRIL = 0.53
BRACO, ANTEBRACO = 0.17, 0.15


@dataclass(frozen=True)
class Postura:
    x: float  # quadril, px
    y: float  # quadril, px
    inclinacao: float = 0.0  # graus do tronco em relação à vertical (90 = deitado)
    braco: float | None = None  # ângulo quadril–ombro–cotovelo dos dois braços; None = braço solto


EM_PE_FORA = Postura(150, QUADRIL_EM_PE)
NA_CAMA = Postura(450, QUADRIL_NA_CAMA, 90)


def _rotacionar(v: np.ndarray, graus: float) -> np.ndarray:
    """Gira no sentido anti-horário num sistema com y para cima."""
    a = np.radians(graus)
    c, s = np.cos(a), np.sin(a)
    return np.array([c * v[0] - s * v[1], s * v[0] + c * v[1]])


def pose(postura: Postura, altura: float = ALTURA, ruido: float = 0.0,
         gerador: np.random.Generator | None = None) -> Pessoa:
    rel = MODELO.copy()
    rel[:, 1] -= ALTURA_QUADRIL  # origem no centro do quadril, y para cima
    if postura.braco is not None:
        for ombro, quadril, cotovelo, punho, sentido in ((5, 11, 7, 9, -1), (6, 12, 8, 10, 1)):
            para_quadril = rel[quadril] - rel[ombro]
            direcao = _rotacionar(para_quadril, sentido * postura.braco)
            direcao /= np.linalg.norm(direcao)
            rel[cotovelo] = rel[ombro] + BRACO * direcao
            rel[punho] = rel[ombro] + (BRACO + ANTEBRACO) * direcao
    # Para a imagem (y para baixo) e gira o corpo inteiro em torno do quadril.
    img = np.column_stack([rel[:, 0], -rel[:, 1]]) * altura
    a = np.radians(postura.inclinacao)
    c, s = np.cos(a), np.sin(a)
    girado = np.column_stack([img[:, 0] * c - img[:, 1] * s, img[:, 0] * s + img[:, 1] * c])
    pontos = girado + [postura.x, postura.y]
    if ruido > 0:
        pontos = pontos + (gerador or np.random.default_rng(SEMENTE)).normal(0, ruido, pontos.shape)
    margem = 0.04 * altura
    caixa = (pontos[:, 0].min() - margem, pontos[:, 1].min() - margem,
             pontos[:, 0].max() + margem, pontos[:, 1].max() + margem)
    return Pessoa(pontos, np.full(17, 0.9), tuple(float(v) for v in caixa), 0.9)


Trecho = tuple[float, Postura | None, Postura | None]  # (duração_s, início, fim); None = ninguém


def _misturar(a: Postura, b: Postura, f: float) -> Postura:
    braco = None if a.braco is None or b.braco is None else a.braco + (b.braco - a.braco) * f
    return Postura(a.x + (b.x - a.x) * f, a.y + (b.y - a.y) * f,
                   a.inclinacao + (b.inclinacao - a.inclinacao) * f, braco)


def cena(trechos: list[Trecho], fps: float = 5.0, leito: Caixa | None = LEITO,
         ruido: float = 0.0, extras: list[Pessoa] | None = None) -> list[QuadroAnalisado]:
    """Monta os quadros de uma cena. ``ruido`` (px) imita o tremor do esqueleto do YOLO."""
    gerador = np.random.default_rng(SEMENTE)
    objetos = [Objeto("bed", leito, 0.8)] if leito else []
    quadros: list[QuadroAnalisado] = []
    t0 = 0.0
    for duracao, inicio, fim in trechos:
        n = int(round(duracao * fps))
        for i in range(n):
            t = t0 + i / fps
            pessoas = list(extras or [])
            if inicio is not None:
                postura = _misturar(inicio, fim or inicio, i / n)
                pessoas.insert(0, pose(postura, ruido=ruido, gerador=gerador))
            quadros.append(QuadroAnalisado(round(t, 6), pessoas, list(objetos)))
        t0 += n / fps
    return quadros


# Cenas prontas da spec (RF-04).

def cena_deitar_devagar_na_cama() -> list[QuadroAnalisado]:
    perto = Postura(420, QUADRIL_EM_PE)
    return cena([(4, EM_PE_FORA, perto), (4, perto, NA_CAMA), (12, NA_CAMA, NA_CAMA)])


LEITO_BAIXO: Caixa = (180.0, 380.0, 520.0, 460.0)  # colchão rente ao chão, onde a cena_queda termina


def cena_despencar_no_leito_baixo() -> list[QuadroAnalisado]:
    """O mesmo movimento da ``cena_queda``, mas o corpo cai sobre o leito: só a zona muda."""
    return cena_queda(leito=LEITO_BAIXO)


def cena_deitar_devagar_no_chao() -> list[QuadroAnalisado]:
    """Deita no chão fora do leito, mas em 5 s: não é queda."""
    no_chao = Postura(150, QUADRIL_NO_CHAO, 90)
    return cena([(4, EM_PE_FORA, None), (5, EM_PE_FORA, no_chao), (10, no_chao, None)])


def cena_levantar_e_sair() -> list[QuadroAnalisado]:
    sentado = Postura(450, QUADRIL_EM_PE - 40)
    porta = Postura(80, QUADRIL_EM_PE)
    return cena([(10, NA_CAMA, None), (2, NA_CAMA, sentado), (3, sentado, porta), (10, porta, None)])


def cena_queda(leito: Caixa | None = LEITO) -> list[QuadroAnalisado]:
    """Em pé fora do leito, cai em 0,6 s e fica 10 s no chão."""
    no_chao = Postura(230, QUADRIL_NO_CHAO, 90)
    return cena([(5, EM_PE_FORA, None), (0.6, EM_PE_FORA, no_chao), (10, no_chao, None)], leito=leito)


def cena_parado(segundos: float = 70) -> list[QuadroAnalisado]:
    return cena([(segundos, NA_CAMA, None)], ruido=0.5)


def emendar(*cenas: list[QuadroAnalisado], fps: float = 5.0) -> list[QuadroAnalisado]:
    """Junta cenas em sequência, renumerando o tempo."""
    quadros = [q for c in cenas for q in c]
    return [replace(q, t_s=round(i / fps, 6)) for i, q in enumerate(quadros)]


def cena_agitacao() -> list[QuadroAnalisado]:
    """2 min deitado calmo (tremor de 0,5 px), 10 s se debatendo (15 px), 20 s calmo de novo."""
    calmo = cena([(120, NA_CAMA, None)], ruido=0.5)
    agitado = cena([(10, NA_CAMA, None)], ruido=15)
    return emendar(calmo, agitado, cena([(20, NA_CAMA, None)], ruido=0.5))


def cena_saida_do_quadro() -> list[QuadroAnalisado]:
    """Fica em pé 5 s, some do quadro por 15 s e volta."""
    return cena([(5, EM_PE_FORA, None), (15, None, None), (5, EM_PE_FORA, None)])


def gravar_video(caminho: Path, imagem: np.ndarray, segundos: float, fps: float, deslocamento_px: int = 0) -> Path:
    """Vídeo ``mp4v`` repetindo ``imagem``; ``deslocamento_px`` por quadro dá algum movimento."""
    altura, largura = imagem.shape[:2]
    escritor = cv2.VideoWriter(str(caminho), cv2.VideoWriter_fourcc(*"mp4v"), fps, (largura, altura))
    for i in range(int(round(segundos * fps))):
        matriz = np.float32([[1, 0, (i * deslocamento_px) % 40], [0, 1, 0]])
        escritor.write(cv2.warpAffine(imagem, matriz, (largura, altura)))
    escritor.release()
    return caminho


def serie_elevacao(picos: list[float], fps: float = 5.0) -> list[QuadroAnalisado]:
    """Uma repetição por pico: sobe de 10° ao pico em 1,5 s, segura 0,6 s, desce em 1,5 s, descansa 1 s."""
    trechos: list[Trecho] = []
    repouso = replace(EM_PE_FORA, braco=10.0)
    for pico in picos:
        alto = replace(repouso, braco=pico)
        trechos += [(1.5, repouso, alto), (0.6, alto, None), (1.5, alto, repouso), (1.0, repouso, None)]
    return cena(trechos, fps=fps, leito=None, ruido=0.5)
