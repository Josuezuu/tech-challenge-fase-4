from __future__ import annotations

import pytest

from monitor.prescricoes.extracao import divergencias, dose_do_texto, extrair, extrair_texto, horas_da_frequencia
from tests.prescricoes.conftest import item

# texto → (medicamento, dose, unidade, via, frequência em horas)
TEXTOS = [
    ("Dipirona 1 g IV de 6/6h", ("dipirona", 1.0, "g", "IV", 6.0)),
    ("dipirona 750 mg endovenosa a cada 6 horas", ("dipirona", 750.0, "mg", "IV", 6.0)),
    ("Heparina 5000 UI SC de 8 em 8 horas", ("heparina", 5000.0, "UI", "SC", 8.0)),
    ("ANLODIPINO 2,5mg VO 1x ao dia", ("anlodipino", 2.5, "mg", "VO", 24.0)),
    ("Metoprolol 50 mg, via oral, 2 vezes ao dia", ("metoprolol", 50.0, "mg", "VO", 12.0)),
    ("Iniciar Insulina 10 UI subcutânea 8/8h", ("insulina", 10.0, "UI", "SC", 8.0)),
    ("Omeprazol 40 mg IV uma vez ao dia", ("omeprazol", 40.0, "mg", "IV", 24.0)),
    ("Suspender: Losartana 50 mg VO de 12/12h", ("losartana", 50.0, "mg", "VO", 12.0)),
    ("Ceftriaxona 1,5 g intramuscular 12/12 h", ("ceftriaxona", 1.5, "g", "IM", 12.0)),
    ("Ajustar: morfina 4mg, SC, de 4 em 4 horas", ("morfina", 4.0, "mg", "SC", 4.0)),
]


@pytest.mark.parametrize("texto,esperado", TEXTOS)
def test_dez_formatos_de_texto(texto, esperado, cliente_simulado):
    e = extrair_texto(texto, cliente_simulado)
    assert (e.medicamento, e.dose, e.unidade, e.via, e.frequencia_h) == esperado
    assert e.origem == "simulado"


@pytest.mark.parametrize("texto,horas", [
    ("de 6/6h", 6), ("12/12 h", 12), ("8 em 8 horas", 8), ("de 4 em 4h", 4), ("a cada 8 horas", 8),
    ("2x ao dia", 12), ("3 vezes ao dia", 8), ("uma vez ao dia", 24), ("duas vezes por dia", 12),
    ("a cada 1,5 horas", 1.5),
])
def test_frequencia_em_horas(texto, horas):
    assert horas_da_frequencia(texto) == horas


def test_sem_frequencia_nem_dose():
    assert horas_da_frequencia("se dor") is None
    assert dose_do_texto("dipirona se dor") is None


def test_dose_com_virgula_e_unidade():
    assert dose_do_texto("2,5mg") == (2.5, "mg")
    assert dose_do_texto("1 g") == (1.0, "g")
    assert dose_do_texto("10 UI") == (10.0, "UI")


def test_divergencia_compara_dose_na_mesma_unidade(cliente_simulado):
    certo = item(0, "dipirona", 1000, via="IV", texto="Dipirona 1 g IV de 6/6h")
    assert divergencias(certo, extrair(certo, cliente_simulado)) == []
    errado = item(0, "dipirona", 500, via="VO", texto="Dipirona 1 g IV de 8/8h")
    assert divergencias(errado, extrair(errado, cliente_simulado)) == ["dose", "via", "frequencia"]
