from datetime import datetime

from monitor.eventos import (
    Alerta, Evento, Fonte, Modalidade, NivelAlerta, Severidade, carregar_alertas, carregar_eventos, salvar_jsonl,
)


def _evento(fonte: Fonte = Fonte.SINAIS_VITAIS) -> Evento:
    return Evento(
        paciente_id="leito-12",
        instante=datetime(2026, 11, 12, 14, 2, 0),
        fonte=fonte,
        tipo="spo2_baixa",
        severidade=Severidade.ALTA,
        descricao="SpO2 88% abaixo de 90%",
        detector="limiar_clinico/v1",
        valor=88.0,
        evidencia={"serie": "results/x.csv"},
    )


def test_evento_ida_e_volta_em_jsonl(tmp_path):
    caminho = tmp_path / "eventos.jsonl"
    salvar_jsonl(caminho, [_evento(), _evento(Fonte.MOVIMENTACAO)])
    lidos = carregar_eventos(caminho)
    assert lidos == [_evento(), _evento(Fonte.MOVIMENTACAO)]


def test_movimentacao_e_video_sao_a_mesma_modalidade():
    assert _evento(Fonte.MOVIMENTACAO).modalidade == Modalidade.VIDEO
    assert _evento(Fonte.VIDEO).modalidade == Modalidade.VIDEO
    assert _evento(Fonte.PRESCRICAO).modalidade == Modalidade.TEXTO_CLINICO


def test_alerta_ida_e_volta(tmp_path):
    alerta = Alerta(
        id="a1", paciente_id="leito-12", instante=datetime(2026, 11, 12, 14, 4), nivel=NivelAlerta.CRITICO,
        regra="concordancia", eventos=(_evento(), _evento(Fonte.VIDEO)), texto="x", texto_origem="simulado",
    )
    caminho = tmp_path / "alertas.jsonl"
    salvar_jsonl(caminho, [alerta])
    assert carregar_alertas(caminho) == [alerta]
    assert alerta.modalidades == ["sinais_vitais", "video"]
