from __future__ import annotations

from datetime import timedelta

import numpy as np

from monitor.eventos import Fonte, Severidade
from monitor.sinais.detectores import MonitorVitais, Supressor
from monitor.sinais.injecao import pressao_sintetica
from tests.sinais.conftest import INICIO, rodar, serie


def test_serie_constante_normal_nao_gera_evento():
    assert rodar(serie(600)) == []


def test_serie_normal_com_ruido_nao_gera_evento():
    assert rodar(serie(600, ruido=True)) == []


def test_spo2_em_86_por_10_s_gera_um_evento_maxima():
    df = serie(300)
    df.loc[120:129, "spo2"] = 86
    eventos = rodar(df)
    assert len(eventos) == 1
    e = eventos[0]
    assert (e.tipo, e.severidade, e.fonte) == ("spo2_baixa", Severidade.MAXIMA, Fonte.SINAIS_VITAIS)
    assert e.instante == INICIO + timedelta(seconds=124)  # 5 s de persistência
    assert e.evidencia["gravacao"] == "teste"
    assert e.evidencia["janela"] == "64-184 s"
    assert e.evidencia["serie"] == "results/evidencias/sinais/leito-12_spo2_baixa_124.csv"


def test_artefato_de_1_s_nao_dispara():
    df = serie(300)
    df.loc[150, "spo2"] = 70
    df.loc[200:203, "fc"] = 150  # 4 s: abaixo da persistência de 5
    assert [e.tipo for e in rodar(df)] == []


def test_degrau_de_fc_dentro_da_faixa_dispara_desvio():
    df = serie(400, ruido=True)
    df.loc[200:, "fc"] += 25  # 80 → 105, ainda abaixo de 120
    eventos = rodar(df)
    assert [(e.tipo, e.severidade) for e in eventos] == [("fc_desvio", Severidade.ALTA)]
    assert 200 <= (eventos[0].instante - INICIO).total_seconds() <= 210


def test_desvio_espera_o_minimo_de_historico():
    df = serie(400, ruido=True)
    df.loc[30:, "fc"] += 25  # degrau com só 30 s de história: o desvio ainda não avalia
    assert [e.tipo for e in rodar(df) if e.tipo == "fc_desvio"] == []


def test_episodio_continuo_de_2_min_gera_um_evento():
    df = serie(400)
    df.loc[150:269, "spo2"] = 90  # ALTA por 120 s
    eventos = rodar(df)
    assert [(e.tipo, e.severidade) for e in eventos] == [("spo2_baixa", Severidade.ALTA)]


def test_supressor_reabre_depois_de_30_s_normal_e_nao_antes():
    df = serie(500)
    df.loc[100:119, "fc"] = 130  # episódio 1
    df.loc[140:159, "fc"] = 130  # 20 s normal no meio: mesmo episódio
    df.loc[200:219, "fc"] = 130  # 40 s normal antes: episódio novo
    instantes = [(e.instante - INICIO).total_seconds() for e in rodar(df) if e.tipo == "fc_alta"]
    assert instantes == [104, 204]


def test_supressor_lembra_a_cada_300_s_e_deixa_passar_escalada():
    df = serie(800)
    df.loc[100:799, "spo2"] = 90  # ALTA contínua por 700 s
    df.loc[150:159, "spo2"] = 86  # escalada para MAXIMA no meio
    eventos = [(int((e.instante - INICIO).total_seconds()), e.severidade) for e in rodar(df)]
    assert eventos == [(104, Severidade.ALTA), (154, Severidade.MAXIMA), (454, Severidade.ALTA),
                       (754, Severidade.ALTA)]


def test_supressor_isolado_por_paciente_e_tipo():
    s = Supressor()
    assert s.permitir("a", "fc_alta", INICIO, Severidade.ALTA)
    assert not s.permitir("a", "fc_alta", INICIO + timedelta(seconds=10), Severidade.ALTA)
    assert s.permitir("b", "fc_alta", INICIO, Severidade.ALTA)
    assert s.permitir("a", "fr_alta", INICIO, Severidade.ALTA)


def test_buraco_na_serie_nao_quebra_nem_dispara():
    df = serie(300)
    df.loc[100:140, "fr"] = np.nan
    assert rodar(df) == []


def test_latencia_medida_por_amostra():
    monitor = MonitorVitais()
    rodar(serie(120), monitor)
    assert len(monitor.latencias_ms) == 120
    assert monitor.latencia_media_ms > 0


def test_pa_sintetica_marcada_na_evidencia():
    df = serie(300)
    df["pas"] = pressao_sintetica(300)
    df.loc[100:109, "pas"] = 85
    eventos = rodar(df, MonitorVitais(gravacao="teste", sinteticas=frozenset({"pas"})))
    assert [e.tipo for e in eventos] == ["pas_baixa"]
    assert eventos[0].evidencia["sintetica"] == "sim"


def test_pressao_sintetica_na_faixa_e_deterministica():
    pa = pressao_sintetica(500, semente=7)
    assert pa.min() >= 110 and pa.max() <= 130 and pa.std() > 0
    assert np.array_equal(pa, pressao_sintetica(500, semente=7))
