from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

from monitor.audio.acustica import AtributosVoz, JanelaVoz, energia_por_quadro, extrair, extrair_de_sinal, marcar_pausas
from monitor.audio.comparacao import comparar, detectar
from monitor.config import RAIZ, SEMENTE, Credenciais
from monitor.eventos import Severidade
from monitor.nuvem.azure_fala import ClienteFala, Palavra
from monitor.nuvem.gravacao import Gravador

TAXA = 16_000
AMOSTRAS = RAIZ / "data" / "amostras" / "audio"
INICIO = datetime(2026, 11, 13, 9, 0, 0)


def fala_sintetica(n_palavras: int, dur_palavra_s: float, intervalo_s: float,
                   pausa_a_cada: int = 0, pausa_s: float = 0.0) -> tuple[np.ndarray, list[Palavra]]:
    """"Palavras" = tom harmônico de 150 Hz com envelope, separadas por silêncio com ruído leve."""
    rng = np.random.default_rng(SEMENTE)
    partes: list[np.ndarray] = []
    palavras: list[Palavra] = []
    t = 0.0
    for i in range(n_palavras):
        n = int(dur_palavra_s * TAXA)
        tempo = np.arange(n) / TAXA
        fase = 2 * np.pi * 150 * tempo + 0.5 * np.sin(2 * np.pi * 3 * tempo)  # leve variação de F0
        tom = np.sin(fase) + 0.5 * np.sin(2 * fase) + 0.25 * np.sin(3 * fase)
        partes.append(0.2 * tom * np.hanning(n))
        palavras.append(Palavra(f"p{i}", round(t, 3), round(t + dur_palavra_s, 3)))
        t += dur_palavra_s
        silencio = pausa_s if pausa_a_cada and (i + 1) % pausa_a_cada == 0 else intervalo_s
        partes.append(np.zeros(int(silencio * TAXA)))
        t += silencio
    sinal = np.concatenate(partes)
    return sinal + 1e-3 * rng.standard_normal(len(sinal)), palavras


@pytest.fixture(scope="module")
def normal() -> AtributosVoz:
    # 0,3 s de palavra + 0,1 s de intervalo = 2,5 palavras/s = 150 ppm
    sinal, palavras = fala_sintetica(75, 0.3, 0.1)
    return extrair_de_sinal(sinal, TAXA, palavras)


@pytest.fixture(scope="module")
def alterado() -> AtributosVoz:
    # palavras mais longas (ritmo menor) e pausa de 1 s a cada 4 palavras
    sinal, palavras = fala_sintetica(60, 0.45, 0.1, pausa_a_cada=4, pausa_s=1.0)
    return extrair_de_sinal(sinal, TAXA, palavras)


def test_pausa_so_conta_a_partir_de_250_ms():
    fala, silencio = -20.0, -80.0
    energia = np.array([fala] * 20 + [silencio] * 8 + [fala] * 20 + [silencio] * 12 + [fala] * 20)
    pausa = marcar_pausas(energia)  # 8 quadros = 200 ms (articulação), 12 = 300 ms (pausa)
    assert not pausa[20:28].any()
    assert pausa[48:60].all()
    assert pausa.sum() == 12


def test_energia_de_quadro_em_dbfs():
    seno = np.sin(2 * np.pi * 440 * np.arange(TAXA) / TAXA)  # potência média 0,5 → −3 dBFS
    assert energia_por_quadro(seno, TAXA) == pytest.approx(np.full(40, -3.01), abs=0.05)


def test_atributos_do_sinal_sintetico(normal):
    m = normal.media()
    assert len(normal.janelas) == 6
    assert m["taxa_fala_ppm"] == pytest.approx(150, abs=8)
    assert m["proporcao_pausa"] == pytest.approx(0.0, abs=0.01)
    assert m["f0_media_hz"] == pytest.approx(150, abs=5)
    assert m["hnr_db"] > 10


def test_mesmo_audio_contra_ele_mesmo_nao_altera(normal):
    r = comparar(normal, normal)
    assert not r.alteracao
    assert all(c.z == pytest.approx(0.0) for c in r.atributos if not np.isnan(c.z))
    assert detectar(r, "p", INICIO) == []


def test_ritmo_menor_e_pausas_longas_geram_evento(normal, alterado):
    r = comparar(normal, alterado)
    nomes = {c.atributo for c in r.alterados}
    assert {"taxa_fala_ppm", "proporcao_pausa", "pausas_por_min"} <= nomes
    eventos = detectar(r, "leito-12", INICIO)
    assert len(eventos) == 1
    e = eventos[0]
    assert (e.tipo, e.severidade, e.instante) == ("alteracao_vocal", Severidade.ALTA, INICIO)
    assert e.valor == len(r.alterados)
    assert "referência do paciente" in e.descricao
    assert "fadiga" not in e.descricao.lower() and "disartria" not in e.descricao.lower()
    assert float(e.evidencia["z_taxa_fala_ppm"]) <= -2


def _com(atributos: AtributosVoz, **mudancas: float) -> AtributosVoz:
    janelas = tuple(JanelaVoz(j.inicio_s, j.fim_s, {**j.valores, **mudancas}) for j in atributos.janelas)
    return AtributosVoz(atributos.duracao_s, janelas)


def test_um_atributo_so_nao_basta_e_f0_media_e_informativa(normal):
    so_pausa = comparar(normal, _com(normal, proporcao_pausa=0.4))
    assert [c.atributo for c in so_pausa.alterados] == ["proporcao_pausa"]
    assert not so_pausa.alteracao
    # F0 média 60 Hz acima (z = 12) não conta: não tem direção de piora
    assert not comparar(normal, _com(normal, proporcao_pausa=0.4, f0_media_hz=210.0)).alteracao
    # dois atributos piorando: alteração
    assert comparar(normal, _com(normal, proporcao_pausa=0.4, energia_db=-40.0)).alteracao


def _amostra(nome: str) -> Path:
    caminho = AMOSTRAS / f"{nome}.wav"
    if not caminho.exists():
        pytest.skip("amostras sintéticas não geradas (scripts/gerar_audios_sinteticos.py)")
    return caminho


def _extrair_amostra(nome: str, tmp_path: Path) -> AtributosVoz:
    wav = _amostra(nome)
    fala = ClienteFala(Credenciais(None, None, None, None, None, "x"), "simulado", Gravador("f", tmp_path))
    return extrair(wav, fala.transcrever(wav))


def test_voz_da_maria_normal_contra_alterada(tmp_path):
    normal_maria = _extrair_amostra("sintetico_normal", tmp_path)
    alterada = _extrair_amostra("sintetico_alterado", tmp_path)
    assert not comparar(normal_maria, normal_maria).alteracao
    r = comparar(normal_maria, alterada)
    assert r.alteracao
    assert {"taxa_fala_ppm", "proporcao_pausa"} <= {c.atributo for c in r.alterados}
