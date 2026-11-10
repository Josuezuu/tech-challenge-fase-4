"""Fisioterapia: contagem de repetições e amplitude do exercício (RF-03).

Máquina de dois estados sobre o ângulo do exercício, quadro a quadro:

    repouso --(ângulo passa de limiar_inicio)--> em repetição
    em repetição --(ângulo volta aquém de limiar_inicio - histerese)--> repouso

Durante a repetição guarda o pico (maior ângulo na elevação lateral, menor
no agachamento). Pico que não chega a ``amplitude_esperada`` gera o Evento
INFO ``amplitude_insuficiente``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np

from monitor.eventos import Evento, Fonte, Severidade
from monitor.video.config import EXERCICIOS, ConfigFisioterapia, Exercicio
from monitor.video.geometria import angulo, mediana_movel
from monitor.video.tipos import Pessoa

DETECTOR = "video.fisioterapia/v1"


@dataclass(frozen=True)
class Repeticao:
    inicio_s: float
    fim_s: float
    pico: float  # graus
    completa: bool


@dataclass(frozen=True)
class ResultadoFisioterapia:
    exercicio: str
    repeticoes: list[Repeticao]
    eventos: list[Evento]
    angulos: list[float]  # ângulo suavizado por quadro (para o vídeo anotado)

    @property
    def total(self) -> int:
        return len(self.repeticoes)

    @property
    def incompletas(self) -> int:
        return sum(not r.completa for r in self.repeticoes)

    @property
    def amplitude_media(self) -> float | None:
        return float(np.mean([r.pico for r in self.repeticoes])) if self.repeticoes else None


def angulo_exercicio(pessoa: Pessoa | None, exercicio: Exercicio) -> float:
    """Ângulo do lado mais visível (maior soma de confiança dos três pontos)."""
    if pessoa is None:
        return float("nan")
    lados = [exercicio.pontos_esquerda, exercicio.pontos_direita]
    lados.sort(key=lambda idx: -float(np.sum(pessoa.confiancas[list(idx)])))
    for a, b, c in lados:  # se o lado mais visível tem ponto NaN, tenta o outro
        valor = angulo(pessoa.pontos[a], pessoa.pontos[b], pessoa.pontos[c])
        if not np.isnan(valor):
            return valor
    return float("nan")


def contar_repeticoes(t_s: Sequence[float], angulos: Sequence[float], exercicio: Exercicio) -> list[Repeticao]:
    """Quadro com ângulo NaN não muda o estado (o esqueleto sumiu por um instante)."""
    sinal = 1.0 if exercicio.crescente else -1.0  # agachamento: compara com o sinal trocado
    inicio_rep = sinal * exercicio.limiar_inicio
    fim_rep = sinal * (exercicio.limiar_inicio - sinal * exercicio.histerese)
    repeticoes: list[Repeticao] = []
    em_repeticao, comeco, pico = False, 0.0, 0.0
    for t, a in zip(t_s, angulos):
        if np.isnan(a):
            continue
        v = sinal * a
        if not em_repeticao and v > inicio_rep:
            em_repeticao, comeco, pico = True, t, v
        elif em_repeticao:
            pico = max(pico, v)
            if v < fim_rep:
                valor = sinal * pico
                completa = sinal * valor >= sinal * exercicio.amplitude_esperada
                repeticoes.append(Repeticao(comeco, t, round(valor, 1), completa))
                em_repeticao = False
    return repeticoes


def analisar_fisioterapia(
    pessoas: Sequence[Pessoa | None],
    t_s: Sequence[float],
    paciente_id: str,
    inicio: datetime,
    cfg: ConfigFisioterapia = ConfigFisioterapia(),
) -> ResultadoFisioterapia:
    exercicio = EXERCICIOS[cfg.exercicio]
    brutos = [angulo_exercicio(p, exercicio) for p in pessoas]
    angulos = mediana_movel(brutos, cfg.suavizacao_quadros)
    repeticoes = contar_repeticoes(t_s, angulos, exercicio)
    eventos = []
    for n, r in enumerate(repeticoes, start=1):
        if r.completa:
            continue
        eventos.append(Evento(
            paciente_id=paciente_id,
            instante=inicio + timedelta(seconds=r.fim_s),
            fonte=Fonte.VIDEO,
            tipo="amplitude_insuficiente",
            severidade=Severidade.INFO,
            descricao=(f"Repetição {n} de {exercicio.nome} chegou a {r.pico:.0f}° "
                       f"(esperado {exercicio.amplitude_esperada:.0f}°)."),
            detector=DETECTOR,
            valor=r.pico,
        ))
    return ResultadoFisioterapia(cfg.exercicio, repeticoes, eventos, [float(a) for a in angulos])
