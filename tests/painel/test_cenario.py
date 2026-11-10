import json
from datetime import datetime

from monitor.cenario import ResultadoFonte, executar, primeiro_existente
from monitor.config import Credenciais
from monitor.eventos import Evento, Fonte, Severidade, carregar_alertas
from monitor.nuvem.openai_llm import ClienteLLM

SEM_CHAVE = ClienteLLM(Credenciais(None, None, None, None, None, "-"), "simulado")


def _evento(fonte: Fonte, minuto: int, sev: Severidade = Severidade.ALTA) -> Evento:
    return Evento("leito-12", datetime(2026, 11, 12, 14, minuto), fonte, f"t_{fonte.value}", sev, "d", "teste/v1")


def test_cenario_com_fonte_ausente_e_fonte_com_erro_nao_cai(tmp_path):
    def sinais(pid, cfg, saida):
        return ResultadoFonte("ok", [_evento(Fonte.SINAIS_VITAIS, 2)])

    def audio(pid, cfg, saida):
        return ResultadoFonte("ok", [_evento(Fonte.AUDIO, 3)])

    def video(pid, cfg, saida):
        return ResultadoFonte("pulada", motivo="sem vídeo")

    def prescricoes(pid, cfg, saida):
        raise RuntimeError("quebrou")

    cenario = {"pacientes": [{"paciente_id": "leito-12", "sinais": {}, "audio": {}, "video": {}, "prescricoes": {}}]}
    fontes = {"sinais": sinais, "audio": audio, "video": video, "prescricoes": prescricoes}
    m = executar(cenario, tmp_path, SEM_CHAVE, fontes)

    f = m["pacientes"]["leito-12"]["fontes"]
    assert f["video"] == {"status": "pulada", "eventos": 0, "motivo": "sem vídeo"}
    assert f["prescricoes"]["status"] == "erro" and "quebrou" in f["prescricoes"]["motivo"]
    assert m["concordancias"] == 1
    assert m["primeira_concordancia"]["modalidades"] == ["audio", "sinais_vitais"]
    assert m["primeira_concordancia"]["segundos_desde_primeiro_evento"] == 60
    assert (tmp_path / "eventos" / "sinais_vitais_leito-12.jsonl").exists()
    alertas = carregar_alertas(tmp_path / "alertas.jsonl")
    assert [a.regra for a in alertas] == ["severidade_alta", "concordancia"]
    assert json.loads((tmp_path / "cenario.json").read_text(encoding="utf-8"))["eventos"] == 2


def test_cenario_limpa_eventos_da_execucao_anterior(tmp_path):
    (tmp_path / "eventos").mkdir()
    velho = tmp_path / "eventos" / "video_fall-01-cam0.jsonl"
    velho.write_text("", encoding="utf-8")
    executar({"pacientes": []}, tmp_path, SEM_CHAVE, {})
    assert not velho.exists()


def test_primeiro_existente(tmp_path):
    (tmp_path / "b.wav").write_bytes(b"")
    assert primeiro_existente(["a.wav", "b.wav"], tmp_path) == tmp_path / "b.wav"
    assert primeiro_existente("a.wav", tmp_path) is None
