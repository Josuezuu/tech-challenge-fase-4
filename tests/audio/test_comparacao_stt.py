import numpy as np
import pytest
import soundfile as sf

from monitor.audio.comparacao_stt import comparar_servicos, distancia_edicao, wer
from monitor.config import Credenciais
from monitor.nuvem.azure_fala import ClienteFala
from monitor.nuvem.gravacao import Gravador, chave_de_arquivo
from monitor.nuvem.openai_llm import ClienteLLM

SEM_CHAVE = Credenciais(None, None, None, None, None, "gpt-4o-mini")


def test_distancia_de_edicao_a_mao():
    assert distancia_edicao("a b c".split(), "a b c".split()) == 0
    assert distancia_edicao("a b c".split(), "a x c".split()) == 1  # substituição
    assert distancia_edicao("a b c".split(), "a c".split()) == 1  # remoção
    assert distancia_edicao("a b c".split(), "a b c d".split()) == 1  # inserção
    assert distancia_edicao([], "a b".split()) == 2


def test_wer_ignora_caixa_acento_e_pontuacao():
    assert wer("Estou com falta de ar.", "estou com FALTA de ar") == 0.0
    assert wer("Não tenho febre", "nao tenho febre!") == 0.0


def test_wer_de_textos_conhecidos():
    # 6 palavras; "dor" → "door" (1 sub), "ontem" removida (1 rem), "muito" inserida (1 ins) = 3/6
    assert wer("senti dor no peito desde ontem", "senti door no peito muito desde") == pytest.approx(3 / 6)
    assert wer("bom dia", "") == 1.0
    with pytest.raises(ValueError):
        wer("", "qualquer coisa")


def test_comparar_servicos_sem_chave_explica_o_motivo(tmp_path):
    wav = tmp_path / "a.wav"
    sf.write(wav, np.zeros(16_000, dtype="float32"), 16_000)
    wav.with_suffix(".txt").write_text("bom dia doutor", encoding="utf-8")
    fala = ClienteFala(SEM_CHAVE, "simulado", Gravador("f", tmp_path))
    llm = ClienteLLM(SEM_CHAVE, "simulado", tmp_path)

    r = comparar_servicos(wav, "bom dia doutor", fala, llm)
    assert r["azure"]["wer"] is None and "simulada" in r["azure"]["motivo"]
    assert r["whisper"]["wer"] is None and "OpenAI" in r["whisper"]["motivo"]


def test_comparar_servicos_com_transcricao_gravada(tmp_path):
    wav = tmp_path / "a.wav"
    sf.write(wav, np.zeros(16_000, dtype="float32"), 16_000)
    gravador = Gravador("f", tmp_path)
    gravador.gravar(chave_de_arquivo(wav, "pt-BR"), {
        "texto": "bom dia doutora", "palavras": [], "idioma": "pt-BR", "duracao_s": 1.0, "servico": "azure"})
    r = comparar_servicos(wav, "bom dia doutor", ClienteFala(SEM_CHAVE, "auto", gravador),
                          ClienteLLM(SEM_CHAVE, "simulado", tmp_path))
    assert r["azure"]["origem"] == "gravado"
    assert r["azure"]["wer"] == pytest.approx(1 / 3)
