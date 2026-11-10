from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from monitor.movimentacao.config import ConfigMovimentacao
from monitor.movimentacao.detector import detectar, detectar_agitacao
from monitor.movimentacao.serie import calcular
from monitor.video.paciente import escolher_paciente
from monitor.video.quarto import EstadoQuadro, calcular_estados, detectar_quedas, estimar_zona
from monitor.video.tipos import QuadroAnalisado
from tests.video import sintetico as s

INICIO = datetime(2026, 11, 12, 14, 3, 30)
N = np.nan


def _estados(quadros: list[QuadroAnalisado]) -> list[EstadoQuadro]:
    zona = estimar_zona(quadros)
    return calcular_estados(quadros, escolher_paciente(quadros, zona), zona)


def _tipos(quadros: list[QuadroAnalisado]) -> list[str]:
    estados = _estados(quadros)
    eventos = detectar_quedas(estados, "leito-12", INICIO) + detectar(estados, "leito-12", INICIO)
    return [e.tipo for e in eventos]


def _estado(t: float, presente: bool = True, no_leito: bool | None = True, movimento: float = N) -> EstadoQuadro:
    return EstadoQuadro(t, presente, np.array([0.0, 0.0]), 90.0, 100.0, no_leito, movimento)


def test_serie_por_janela_com_valores_feitos_a_mao():
    estados = (
        [_estado(t, movimento=0.1) for t in (0, 2, 4, 6, 8)]
        + [_estado(10, movimento=0.2), _estado(12, no_leito=False, movimento=0.4),
           _estado(14, presente=False, no_leito=False), _estado(16, presente=False, no_leito=False),
           _estado(18, no_leito=False)]
    )
    serie = calcular(estados, janela_s=10)
    assert serie["inicio_s"].tolist() == [0, 10]
    assert serie["movimento"].tolist() == pytest.approx([0.1, 0.3])
    assert serie["no_leito"].tolist() == pytest.approx([1.0, 0.2])
    assert serie["presente"].tolist() == pytest.approx([1.0, 0.6])
    sem_zona = calcular([_estado(0, no_leito=None, movimento=0.1)])
    assert np.isnan(sem_zona["no_leito"][0])


def test_deitar_na_cama_nao_gera_evento():
    assert _tipos(s.cena_deitar_devagar_na_cama()) == []


def test_levantar_e_sair_gera_uma_saida_do_leito():
    estados = _estados(s.cena_levantar_e_sair())
    eventos = detectar(estados, "leito-12", INICIO)
    assert [e.tipo for e in eventos] == ["saida_do_leito"]
    assert eventos[0].fonte.value == "movimentacao" and eventos[0].severidade.name == "ALTA"
    assert 10 <= (eventos[0].instante - INICIO).total_seconds() <= 15


def test_virar_na_borda_do_leito_por_1_s_nao_e_saida():
    borda = s.Postura(250, s.QUADRIL_NA_CAMA, 90)  # quadril fora da zona por 1 s
    quadros = s.cena([(10, s.NA_CAMA, None), (1, borda, None), (10, s.NA_CAMA, None)])
    assert "saida_do_leito" not in _tipos(quadros)


def test_parado_70_s_gera_uma_imobilidade_prolongada():
    eventos = detectar(_estados(s.cena_parado(70)), "leito-12", INICIO)
    assert [e.tipo for e in eventos] == ["imobilidade_prolongada"]
    assert eventos[0].valor == pytest.approx(69.8, abs=0.5)


def test_parado_50_s_nao_e_imobilidade():
    assert _tipos(s.cena_parado(50)) == []


def test_pico_de_agitacao_numa_serie_calma_gera_um_evento():
    eventos = [e for e in detectar(_estados(s.cena_agitacao()), "leito-12", INICIO)
               if e.tipo == "movimentacao_atipica"]
    assert len(eventos) == 1
    assert (eventos[0].instante - INICIO).total_seconds() == 120
    assert eventos[0].valor > 4


def test_agitacao_precisa_de_seis_janelas_de_historico():
    serie = pd.DataFrame({"inicio_s": [0, 10, 20, 30, 40, 50], "fim_s": [10, 20, 30, 40, 50, 60],
                          "movimento": [0.01, 0.01, 0.01, 0.01, 0.01, 1.0], "presente": [1.0] * 6})
    assert detectar_agitacao(serie, "x", INICIO) == []
    cfg = ConfigMovimentacao(min_janelas=5)
    assert len(detectar_agitacao(serie, "x", INICIO, cfg)) == 1
