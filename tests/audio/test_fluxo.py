from datetime import datetime

import pytest

from monitor.audio.analise import analisar
from monitor.audio.avaliacao import avaliar
from monitor.audio.fluxo import Clientes, processar
from monitor.config import RAIZ, Credenciais
from monitor.nuvem.azure_fala import ClienteFala, Transcricao
from monitor.nuvem.azure_linguagem import ClienteLinguagem
from monitor.nuvem.gravacao import Gravador
from monitor.nuvem.openai_llm import ClienteLLM

AMOSTRAS = RAIZ / "data" / "amostras" / "audio"
SEM_CHAVE = Credenciais(None, None, None, None, None, "gpt-4o-mini")
INICIO = datetime(2026, 11, 13, 9, 0, 0)


@pytest.fixture
def clientes(tmp_path) -> Clientes:
    return Clientes(
        ClienteFala(SEM_CHAVE, "simulado", Gravador("f", tmp_path)),
        ClienteLinguagem(SEM_CHAVE, "simulado", Gravador("l", tmp_path)),
        ClienteLLM(SEM_CHAVE, "simulado", tmp_path),
    )


@pytest.fixture
def amostras():
    if not (AMOSTRAS / "sintetico_termos.wav").exists():
        pytest.skip("amostras sintéticas não geradas (scripts/gerar_audios_sinteticos.py)")
    return AMOSTRAS


def test_transcricao_vazia_nao_chama_o_servico():
    vazia = Transcricao("", (), "pt-BR", 1.0, "azure", "real")
    assert analisar(vazia).entidades == ()


def test_fluxo_da_amostra_de_termos(amostras, clientes, tmp_path):
    r = processar(amostras / "sintetico_termos.wav", "leito-12", INICIO, clientes=clientes, dir_saida=tmp_path)
    termos = [e for e in r.eventos if e.tipo == "termo_critico"]
    assert [e.evidencia["termo"] for e in termos] == ["falta de ar", "dor no peito", "tontura"]
    assert all(e.evidencia["audio"] == "data/amostras/audio/sintetico_termos.wav" for e in r.eventos)
    assert r.voz is None
    assert r.stt["azure"]["wer"] is None  # transcrição simulada
    assert r.to_dict()["origens"] == {"transcricao": "simulado", "analise": "simulado"}


def test_avaliacao_das_amostras_sinteticas(amostras, clientes, tmp_path):
    normal = amostras / "sintetico_normal.wav"
    resultado = avaliar([(normal, normal), (normal, amostras / "sintetico_alterado.wav")], clientes,
                        dir_saida=tmp_path)
    resumo = resultado["resumo"]
    assert (resumo["acertos_alteracao"], resumo["pares_com_gabarito"]) == (2, 2)
    assert resumo["so_amostras_sinteticas"] is True
    assert resultado["pares"][1]["z"]["taxa_fala_ppm"] <= -2
