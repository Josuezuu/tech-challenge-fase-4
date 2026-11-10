from __future__ import annotations

import pandas as pd
import pytest

from monitor.sinais.injecao import TIPOS, Especificacao, plantar, plantar_aleatorio, sortear
from tests.sinais.conftest import serie


def test_original_intocado_e_anomalia_so_na_janela():
    df = serie(481, ruido=True)
    copia = df.copy()
    plantado, rotulos = plantar(df, [Especificacao("taquicardia", 200, 60)])
    pd.testing.assert_frame_equal(df, copia)
    assert rotulos[0].inicio_s == 200 and rotulos[0].fim_s == 260 and rotulos[0].variavel == "fc"
    mudou = plantado["fc"] != df["fc"]
    assert plantado.loc[mudou, "t_s"].between(200, 260).all()
    assert (plantado.loc[210:250, "fc"] - df.loc[210:250, "fc"]).between(40, 60).all()


@pytest.mark.parametrize("tipo,variavel,faixa", [
    ("queda_spo2", "spo2", (82, 86)),
    ("bradicardia", "fc", (33, 47)),
    ("taquipneia", "fr", (30, 35)),
])
def test_tipos_com_alvo_chegam_ao_alvo(tipo, variavel, faixa):
    plantado, rotulos = plantar(serie(481), [Especificacao(tipo, 150, 90)])
    meio = plantado.loc[190:200, variavel]
    assert meio.between(*faixa).all()
    assert rotulos[0].variavel == variavel == TIPOS[tipo]


def test_queda_spo2_em_quem_ja_vive_baixo_cai_pelo_menos_6_pontos():
    plantado, _ = plantar(serie(481, spo2=85), [Especificacao("queda_spo2", 150, 90)])
    assert plantado.loc[195, "spo2"] <= 79


def test_degrau_fc_e_seco():
    plantado, _ = plantar(serie(481), [Especificacao("degrau_fc", 100, 30)])
    assert plantado.loc[99, "fc"] == 80 and 100 <= plantado.loc[100, "fc"] <= 105


def test_plantar_aleatorio_deterministico_e_sem_sobreposicao():
    df = serie(481, ruido=True)
    a, ra = plantar_aleatorio(df, 2, semente=3)
    b, rb = plantar_aleatorio(df, 2, semente=3)
    pd.testing.assert_frame_equal(a, b)
    assert ra == rb and len(ra) == 2
    assert ra[0].fim_s + 60 <= ra[1].inicio_s
    assert all(30 <= r.fim_s - r.inicio_s <= 90 and r.inicio_s >= 90 for r in ra)
    _, rc = plantar_aleatorio(df, 2, semente=4)
    assert rc != ra


def test_sortear_falha_claro_quando_nao_cabe():
    with pytest.raises(ValueError, match="não coube"):
        sortear(serie(200), 5)


def test_tipo_desconhecido():
    with pytest.raises(ValueError, match="desconhecido"):
        plantar(serie(100), [Especificacao("hipotermia", 10, 30)])
