import numpy as np
import pytest

from monitor.video import geometria as g

N = np.nan


def _pontos(**marcados: tuple[float, float]) -> np.ndarray:
    nomes = {"ombro_e": 5, "ombro_d": 6, "quadril_e": 11, "quadril_d": 12}
    p = np.full((17, 2), np.nan)
    for nome, xy in marcados.items():
        p[nomes[nome]] = xy
    return p


def test_angulo_reto_raso_e_com_nan():
    assert g.angulo(np.array([1, 0]), np.array([0, 0]), np.array([0, 1])) == pytest.approx(90)
    assert g.angulo(np.array([-1, 0]), np.array([0, 0]), np.array([1, 0])) == pytest.approx(180)
    assert np.isnan(g.angulo(np.array([N, 0]), np.array([0, 0]), np.array([1, 0])))


def test_inclinacao_em_pe_deitado_e_quadril_de_um_lado_so():
    em_pe = _pontos(ombro_e=(90, 100), ombro_d=(110, 100), quadril_e=(92, 200), quadril_d=(108, 200))
    deitado = _pontos(ombro_e=(100, 300), ombro_d=(100, 310), quadril_e=(200, 300), quadril_d=(200, 310))
    so_um_quadril = _pontos(ombro_e=(90, 100), ombro_d=(110, 100), quadril_e=(100, 200))
    assert g.inclinacao_tronco(em_pe) == pytest.approx(0, abs=1e-6)
    assert g.inclinacao_tronco(deitado) == pytest.approx(90)
    assert g.centro_quadril(so_um_quadril).tolist() == [100, 200]
    assert np.isnan(g.inclinacao_tronco(_pontos(ombro_e=(0, 0))))


def test_tamanho_do_corpo_independe_da_orientacao():
    assert g.tamanho_corpo((0, 0, 50, 180)) == 180
    assert g.tamanho_corpo((0, 0, 180, 50)) == 180


def test_deslocamento_medio_normalizado_ignora_pontos_ausentes():
    a = np.zeros((17, 2))
    b = a.copy()
    b[:, 0] = 10
    b[3] = np.nan
    assert g.deslocamento_medio(a, b, 100) == pytest.approx(0.1)


def test_mediana_movel_remove_pico_isolado_e_tolera_nan():
    s = g.mediana_movel([10, 10, 90, 10, 10, N, 10], 3)
    assert s.tolist() == [10, 10, 10, 10, 10, 10, 10]


def test_zona_ampliada_e_ponto_no_poligono():
    caixa = g.ampliar_caixa((100, 100, 200, 300), 0.10)
    assert caixa == pytest.approx((95, 90, 205, 310))
    x1, y1, x2, y2 = caixa
    poligono = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
    assert g.ponto_no_poligono(np.array([150, 200]), poligono)
    assert g.ponto_no_poligono(np.array([97, 305]), poligono)
    assert not g.ponto_no_poligono(np.array([250, 200]), poligono)
    assert not g.ponto_no_poligono(np.array([N, 200]), poligono)
