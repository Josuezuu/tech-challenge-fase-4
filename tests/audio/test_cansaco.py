import numpy as np

from monitor.audio import acustica, comparacao
from monitor.audio.cansaco import NIVEIS, cansar
from monitor.nuvem.azure_fala import Palavra

TAXA = 16_000


def _fala(n_palavras: int = 30, palavra_s: float = 0.35, intervalo_s: float = 0.1, semente: int = 1):
    """Tom com vibrato em rajadas (uma por palavra), separadas por silêncio curto."""
    rng = np.random.default_rng(semente)
    pedacos, palavras, t = [], [], 0.0
    for i in range(n_palavras):
        n = int(palavra_s * TAXA)
        tt = np.arange(n) / TAXA
        f0 = 140 + 15 * np.sin(2 * np.pi * 3 * tt) + rng.normal(0, 1)
        pedacos += [0.3 * np.sin(2 * np.pi * np.cumsum(f0) / TAXA), np.zeros(int(intervalo_s * TAXA))]
        palavras.append(Palavra(f"p{i}", t, t + palavra_s))
        t += palavra_s + intervalo_s
    sinal = np.concatenate(pedacos) + rng.normal(0, 1e-4, sum(len(p) for p in pedacos))
    return sinal, tuple(palavras)


def test_cansar_alonga_insere_pausas_e_enfraquece():
    sinal, palavras = _fala()
    y, novas = cansar(sinal, TAXA, palavras, "moderada")
    n = NIVEIS["moderada"]
    pausas = (len(palavras) - 1) // n.pausa_a_cada
    assert abs(len(y) / TAXA - (len(sinal) / TAXA * n.lentidao + pausas * n.pausa_s)) < 0.05
    assert len(novas) == len(palavras)
    assert novas[-1].fim_s > palavras[-1].fim_s * n.lentidao  # tempos deslocados pelas pausas
    energia = acustica.extrair_de_sinal(sinal, TAXA, palavras).media()["energia_db"]
    energia_cansada = acustica.extrair_de_sinal(y, TAXA, novas).media()["energia_db"]
    assert energia_cansada < energia - 3  # voz mais fraca


def test_voz_cansada_acusa_e_original_nao():
    sinal, palavras = _fala()
    ref = acustica.extrair_de_sinal(sinal, TAXA, palavras)
    assert not comparacao.comparar(ref, ref).alteracao
    y, novas = cansar(sinal, TAXA, palavras, "forte")
    assert comparacao.comparar(ref, acustica.extrair_de_sinal(y, TAXA, novas)).alteracao
