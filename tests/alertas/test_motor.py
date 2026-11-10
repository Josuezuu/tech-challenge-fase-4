from __future__ import annotations

import random
from datetime import datetime, timedelta

from monitor.alertas.avaliacao import avaliar, latencia_ponta_a_ponta
from monitor.alertas.motor import MotorAlertas
from monitor.eventos import Evento, Fonte, NivelAlerta, Severidade

T0 = datetime(2026, 11, 12, 14, 0, 0)


def ev(minuto: float, fonte: Fonte, tipo: str, sev: Severidade, paciente: str = "leito-12") -> Evento:
    return Evento(paciente_id=paciente, instante=T0 + timedelta(minutes=minuto), fonte=fonte, tipo=tipo,
                  severidade=sev, descricao=f"{tipo} observado", detector="teste/v1", valor=1.0,
                  evidencia={"serie": f"results/{tipo}.csv"})


def resumo(alertas):  # noqa: ANN001, ANN201
    return [(a.instante.strftime("%H:%M"), a.nivel, a.regra, len(a.eventos)) for a in alertas]


def test_cenario_spo2_seguido_de_queda():
    spo2 = ev(2, Fonte.SINAIS_VITAIS, "spo2_baixa", Severidade.ALTA)
    queda = ev(4, Fonte.VIDEO, "queda", Severidade.MAXIMA)
    alertas = MotorAlertas().processar_todos([queda, spo2])
    assert resumo(alertas) == [
        ("14:02", NivelAlerta.ATENCAO, "severidade_alta", 1),
        ("14:04", NivelAlerta.CRITICO, "concordancia", 2),
    ]
    assert alertas[1].eventos == (spo2, queda)  # evidência intacta, em ordem
    assert alertas[1].modalidades == ["sinais_vitais", "video"]
    assert latencia_ponta_a_ponta(alertas[1]) == 120


def test_no_maximo_um_alerta_por_evento():
    eventos = [ev(m, f, t, s) for m, f, t, s in [
        (1, Fonte.SINAIS_VITAIS, "fc_alta", Severidade.ALTA),
        (2, Fonte.AUDIO, "dor", Severidade.MAXIMA),
        (3, Fonte.VIDEO, "queda", Severidade.MAXIMA),
        (4, Fonte.PRESCRICAO, "prescricao_dose_excessiva", Severidade.INFO),
    ]]
    motor = MotorAlertas()
    assert all(len(motor.processar(e)) <= 1 for e in eventos)


def test_video_e_movimentacao_nao_concordam():
    alertas = MotorAlertas().processar_todos([
        ev(0, Fonte.VIDEO, "agitacao", Severidade.ALTA),
        ev(1, Fonte.MOVIMENTACAO, "saida_do_leito", Severidade.ALTA),
    ])
    assert [a.regra for a in alertas] == ["severidade_alta", "severidade_alta"]


def test_onze_minutos_nao_concordam_e_dez_concordam():
    longe = MotorAlertas().processar_todos([
        ev(0, Fonte.SINAIS_VITAIS, "spo2_baixa", Severidade.ALTA),
        ev(11, Fonte.AUDIO, "dor", Severidade.ALTA),
    ])
    assert [a.regra for a in longe] == ["severidade_alta", "severidade_alta"]
    perto = MotorAlertas().processar_todos([
        ev(0, Fonte.SINAIS_VITAIS, "spo2_baixa", Severidade.ALTA),
        ev(10, Fonte.AUDIO, "dor", Severidade.ALTA),
    ])
    assert [a.regra for a in perto] == ["severidade_alta", "concordancia"]


def test_info_nao_entra_na_concordancia():
    alertas = MotorAlertas().processar_todos([
        ev(0, Fonte.PRESCRICAO, "prescricao_texto_divergente", Severidade.INFO),
        ev(1, Fonte.SINAIS_VITAIS, "fc_alta", Severidade.ALTA),
    ])
    assert [(a.nivel, a.regra) for a in alertas] == [
        (NivelAlerta.INFORMATIVO, "informativo"), (NivelAlerta.ATENCAO, "severidade_alta")]


def test_concordancia_nao_repete_sem_modalidade_nova():
    alertas = MotorAlertas().processar_todos([
        ev(0, Fonte.SINAIS_VITAIS, "spo2_baixa", Severidade.ALTA),
        ev(1, Fonte.VIDEO, "queda", Severidade.ALTA),
        ev(2, Fonte.SINAIS_VITAIS, "fc_alta", Severidade.ALTA),  # mesmas modalidades: não repete
        ev(3, Fonte.AUDIO, "dor", Severidade.ALTA),  # modalidade nova: outro CRÍTICO
    ])
    assert [a.regra for a in alertas] == ["severidade_alta", "concordancia", "severidade_alta", "concordancia"]
    assert len(alertas[3].eventos) == 4


def test_concordancia_volta_depois_que_a_janela_expira():
    alertas = MotorAlertas().processar_todos([
        ev(0, Fonte.SINAIS_VITAIS, "spo2_baixa", Severidade.ALTA),
        ev(1, Fonte.VIDEO, "queda", Severidade.ALTA),
        ev(12, Fonte.SINAIS_VITAIS, "spo2_baixa", Severidade.ALTA),
        ev(13, Fonte.VIDEO, "queda", Severidade.ALTA),
    ])
    assert [a.regra for a in alertas] == ["severidade_alta", "concordancia", "severidade_alta", "concordancia"]
    assert len(alertas[3].eventos) == 2  # os de 14:00/14:01 já saíram da janela


def test_intervalo_minimo_por_paciente_tipo_nivel():
    alertas = MotorAlertas().processar_todos([
        ev(0, Fonte.SINAIS_VITAIS, "fc_alta", Severidade.ALTA),
        ev(3, Fonte.SINAIS_VITAIS, "fc_alta", Severidade.ALTA),  # < 5 min: suprimido
        ev(3, Fonte.SINAIS_VITAIS, "fc_alta", Severidade.MAXIMA),  # outro nível: passa
        ev(3, Fonte.SINAIS_VITAIS, "fc_alta", Severidade.ALTA, paciente="leito-7"),  # outro paciente
        ev(6, Fonte.SINAIS_VITAIS, "fc_alta", Severidade.ALTA),  # ≥ 5 min: passa
    ])
    assert [(a.instante.minute, a.paciente_id, a.regra) for a in alertas] == [
        (0, "leito-12", "severidade_alta"), (3, "leito-12", "severidade_maxima"),
        (3, "leito-7", "severidade_alta"), (6, "leito-12", "severidade_alta")]


def test_ordem_embaralhada_da_o_mesmo_resultado():
    eventos = [ev(m, f, t, s, p) for m, f, t, s, p in [
        (0, Fonte.SINAIS_VITAIS, "spo2_baixa", Severidade.ALTA, "leito-12"),
        (1, Fonte.AUDIO, "dor", Severidade.ALTA, "leito-12"),
        (1, Fonte.VIDEO, "queda", Severidade.MAXIMA, "leito-7"),
        (2, Fonte.SINAIS_VITAIS, "fc_alta", Severidade.ALTA, "leito-7"),
        (2, Fonte.PRESCRICAO, "prescricao_texto_divergente", Severidade.INFO, "leito-7"),
        (5, Fonte.MOVIMENTACAO, "saida_do_leito", Severidade.ALTA, "leito-12"),
        (20, Fonte.SINAIS_VITAIS, "spo2_baixa", Severidade.MAXIMA, "leito-12"),
    ]]
    referencia = MotorAlertas().processar_todos(eventos)
    for semente in range(5):
        embaralhados = eventos[:]
        random.Random(semente).shuffle(embaralhados)
        assert MotorAlertas().processar_todos(embaralhados) == referencia


def test_avaliar_conta_niveis_e_latencia():
    alertas = MotorAlertas().processar_todos([
        ev(2, Fonte.SINAIS_VITAIS, "spo2_baixa", Severidade.ALTA),
        ev(4, Fonte.VIDEO, "queda", Severidade.MAXIMA),
    ])
    r = avaliar(alertas)
    assert r["por_nivel"] == {"ATENCAO": 1, "CRITICO": 1}
    assert r["latencia_ponta_a_ponta_s"]["primeira"] == 120
