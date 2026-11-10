from __future__ import annotations

from datetime import timedelta

from monitor.sinais import fluxo
from tests.sinais.conftest import INICIO, serie


def test_reproduz_na_ordem_com_instante_inicio_mais_t():
    df = serie(10).sample(frac=1, random_state=1)  # embaralhada
    amostras = list(fluxo.reproduzir(df, "leito-12", INICIO))
    assert [a.t_s for a in amostras] == list(range(10))
    assert all(a.instante == INICIO + timedelta(seconds=a.t_s) for a in amostras)
    assert amostras[0].paciente_id == "leito-12"
    assert set(amostras[0].valores) == {"fc", "pulso", "fr", "spo2"}


def test_velocidade_none_nao_dorme_e_60_dorme_um_sessenta_avos(monkeypatch):
    dormidas: list[float] = []
    monkeypatch.setattr(fluxo.time, "sleep", dormidas.append)
    list(fluxo.reproduzir(serie(5), "p", INICIO))
    assert dormidas == []
    list(fluxo.reproduzir(serie(5), "p", INICIO, velocidade=60))
    assert dormidas == [1 / 60] * 5
