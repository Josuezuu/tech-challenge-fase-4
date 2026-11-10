from __future__ import annotations

from monitor.sinais.avaliacao import avaliar, fora_da_faixa_na_mediana
from tests.sinais.conftest import serie


def _gravacoes() -> dict[str, object]:
    return {f"sint_{i}": serie(481, fc=70 + 5 * i, ruido=True) for i in range(4)}


def test_anomalias_plantadas_sao_encontradas_e_serie_limpa_nao_alarma():
    r = avaliar(_gravacoes(), n_anomalias=2, semente=1)
    assert r["geral"]["rotulos"] == 8
    assert r["geral"]["recall"] == 1.0
    assert r["geral"]["precisao"] == 1.0
    assert r["sem_plantio"]["eventos"] == 0
    assert r["sem_plantio"]["alertas_falsos_por_hora"] == 0
    assert 0 < r["geral"]["atraso_medio_s"] < 30
    assert sum(t["rotulos"] for t in r["por_tipo"].values()) == 8


def test_reproduzivel_com_a_mesma_semente():
    a = avaliar(_gravacoes(), 2, semente=5)
    b = avaliar(_gravacoes(), 2, semente=5)
    a.pop("latencia_media_ms"), b.pop("latencia_media_ms")  # tempo de máquina varia
    assert a == b


def test_condicao_real_pela_mediana():
    assert fora_da_faixa_na_mediana(serie(100, fc=125, spo2=85)) == ["spo2", "fc"]
    assert fora_da_faixa_na_mediana(serie(100)) == []
