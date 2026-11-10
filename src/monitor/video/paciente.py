"""Qual das pessoas do quadro é o paciente.

Regra inicial: a pessoa mais perto do centro da zona do leito; sem leito, a
maior caixa (quem está mais perto da câmera). Depois, rastreamento por
proximidade: em cada quadro, a pessoa cuja caixa está mais perto da caixa do
paciente no último quadro em que ele foi visto, desde que a distância não
passe de ``salto_max_corpos`` tamanhos de corpo. Se o paciente some por mais
de ``perda_max_s``, volta para a regra inicial.

Não é ReID: uma enfermeira que passa colada ao paciente pode roubar o
rastreamento. Para o quarto de um leito só, basta.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from monitor.video.config import ConfigPaciente
from monitor.video.geometria import centro_caixa, centro_quadril, tamanho_corpo
from monitor.video.tipos import Pessoa, Poligono, QuadroAnalisado


def _escolha_inicial(pessoas: Sequence[Pessoa], zona: Poligono | None) -> Pessoa | None:
    if not pessoas:
        return None
    if zona is None:
        return max(pessoas, key=lambda p: tamanho_corpo(p.caixa))
    centro_leito = np.mean(np.array(zona, dtype=float), axis=0)

    def distancia(p: Pessoa) -> float:
        ponto = centro_quadril(p.pontos)
        if np.isnan(ponto).any():
            ponto = centro_caixa(p.caixa)
        return float(np.linalg.norm(ponto - centro_leito))

    return min(pessoas, key=distancia)


def _mais_proxima(pessoas: Sequence[Pessoa], anterior: Pessoa, salto_max_corpos: float) -> Pessoa | None:
    if not pessoas:
        return None
    ref = centro_caixa(anterior.caixa)
    escolhida = min(pessoas, key=lambda p: float(np.linalg.norm(centro_caixa(p.caixa) - ref)))
    distancia = float(np.linalg.norm(centro_caixa(escolhida.caixa) - ref))
    return escolhida if distancia <= salto_max_corpos * tamanho_corpo(anterior.caixa) else None


def escolher_paciente(
    quadros: Sequence[QuadroAnalisado],
    zona: Poligono | None,
    cfg: ConfigPaciente = ConfigPaciente(),
) -> list[Pessoa | None]:
    """Uma entrada por quadro: a pessoa que é o paciente, ou ``None`` se ele não está."""
    escolhidos: list[Pessoa | None] = []
    ultima: Pessoa | None = None
    t_ultima = float("-inf")
    for q in quadros:
        if ultima is None or q.t_s - t_ultima > cfg.perda_max_s:
            atual = _escolha_inicial(q.pessoas, zona)
        else:
            atual = _mais_proxima(q.pessoas, ultima, cfg.salto_max_corpos)
        if atual is not None:
            ultima, t_ultima = atual, q.t_s
        escolhidos.append(atual)
    return escolhidos
