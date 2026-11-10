import numpy as np
import pytest
import soundfile as sf

from monitor.audio.conversao import para_wav


def test_estereo_44k_vira_mono_16k_e_copia_roteiro(tmp_path):
    taxa = 44_100
    t = np.arange(taxa * 2) / taxa
    estereo = np.stack([0.3 * np.sin(2 * np.pi * 220 * t), 0.3 * np.sin(2 * np.pi * 330 * t)], axis=1)
    entrada = tmp_path / "consulta.wav"
    sf.write(entrada, estereo.astype("float32"), taxa)
    entrada.with_suffix(".txt").write_text("Bom dia.", encoding="utf-8")

    saida = para_wav(entrada, tmp_path / "saida" / "consulta.wav")

    info = sf.info(str(saida))
    assert (info.samplerate, info.channels, info.subtype) == (16_000, 1, "PCM_16")
    assert info.duration == pytest.approx(2.0, abs=0.01)
    assert saida.with_suffix(".txt").read_text(encoding="utf-8") == "Bom dia."


def test_saida_igual_a_entrada_e_recusada(tmp_path):
    entrada = tmp_path / "a.wav"
    sf.write(entrada, np.zeros(16_000, dtype="float32"), 16_000)
    with pytest.raises(ValueError):
        para_wav(entrada, entrada)
