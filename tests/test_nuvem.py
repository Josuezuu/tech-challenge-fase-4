import numpy as np
import pytest
import soundfile as sf

from monitor.config import Credenciais
from monitor.nuvem.azure_fala import ClienteFala
from monitor.nuvem.azure_linguagem import ClienteLinguagem
from monitor.nuvem.gravacao import Gravador, usar_servico_real
from monitor.nuvem.openai_llm import ClienteLLM

SEM_CHAVE = Credenciais(None, None, None, None, None, "gpt-4o-mini")


@pytest.fixture
def wav(tmp_path):
    caminho = tmp_path / "a1.wav"
    sf.write(caminho, np.zeros(16000 * 4, dtype="float32"), 16000)
    caminho.with_suffix(".txt").write_text("Estou com falta de ar desde ontem.", encoding="utf-8")
    return caminho


def test_modo_real_sem_chave_falha():
    with pytest.raises(RuntimeError):
        usar_servico_real(False, "real", "X")
    assert usar_servico_real(True, "auto", "X") is True
    assert usar_servico_real(True, "simulado", "X") is False


def test_fala_simulada_usa_roteiro_e_distribui_palavras(wav, tmp_path):
    cliente = ClienteFala(SEM_CHAVE, "auto", Gravador("f", tmp_path))
    t = cliente.transcrever(wav)
    assert t.origem == "simulado"
    assert t.texto.startswith("Estou com falta de ar")
    assert len(t.palavras) == 7
    assert t.palavras[-1].fim_s == pytest.approx(4.0, abs=0.01)


def test_fala_prefere_gravacao_a_simulacao(wav, tmp_path):
    gravador = Gravador("f", tmp_path)
    cliente = ClienteFala(SEM_CHAVE, "auto", gravador)
    from monitor.nuvem.gravacao import chave_de_arquivo

    gravador.gravar(chave_de_arquivo(wav, "pt-BR"), {
        "texto": "texto real", "palavras": [], "idioma": "pt-BR", "duracao_s": 4.0, "servico": "azure"})
    assert cliente.transcrever(wav).origem == "gravado"
    assert cliente.transcrever(wav).texto == "texto real"


def test_linguagem_simulada_acha_sintoma_negacao_e_sentimento(tmp_path):
    cliente = ClienteLinguagem(SEM_CHAVE, "auto", Gravador("l", tmp_path))
    a = cliente.analisar("Estou com falta de ar e dor no peito. Não tenho febre. Hoje estou melhor.")
    categorias = {(e.texto.lower(), e.categoria, e.negada) for e in a.entidades}
    assert ("falta de ar", "SymptomOrSign", False) in categorias
    assert ("dor no peito", "SymptomOrSign", False) in categorias
    assert ("febre", "SymptomOrSign", True) in categorias
    assert a.frases[0].sentimento == "negative"
    assert a.frases[-1].sentimento == "positive"
    assert a.sentimento == "mixed"


def test_entidades_de_prescricao(tmp_path):
    cliente = ClienteLinguagem(SEM_CHAVE, "auto", Gravador("l", tmp_path))
    ents, origem = cliente.entidades_saude("Dipirona 1 g IV de 6/6h")
    assert origem == "simulado"
    cats = {e.categoria: e.texto for e in ents}
    assert cats["MedicationName"].lower() == "dipirona"
    assert cats["Dosage"] == "1 g"
    assert cats["MedicationRoute"] == "IV"
    assert "6/6h" in cats["Frequency"]


def test_llm_simulado_usa_modelo_fixo(tmp_path):
    cliente = ClienteLLM(SEM_CHAVE, "auto", tmp_path)
    r = cliente.redigir("instr", {"a": 1}, lambda d: f"valor {d['a']}")
    assert (r.texto, r.origem) == ("valor 1", "simulado")


def test_whisper_sem_chave_devolve_none(wav, tmp_path):
    assert ClienteLLM(SEM_CHAVE, "auto", tmp_path).transcrever_whisper(wav) is None
