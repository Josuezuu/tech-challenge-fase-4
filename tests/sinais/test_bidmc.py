from __future__ import annotations

import math

import pytest

import scripts.baixar_bidmc as baixar_bidmc
from monitor.sinais import bidmc

CSV_A_MAO = """Time [s], HR, PULSE, RESP, SpO2
0,94,93,25,97
1,94,93,25,97
2,94,93,,97
3,92,93,26,97
4,NaN,93,26,97
5,93,92,26,96
6,93,92,26,96
7,93,92,26,96
8,93,92,26,96
9,93,92,26,96
"""


def test_ler_numerics_limpa_colunas_e_tolera_nan(tmp_path):
    caminho = tmp_path / "bidmc_99_Numerics.csv"
    caminho.write_text(CSV_A_MAO, encoding="utf-8")
    df = bidmc.ler_numerics(caminho)
    assert list(df.columns) == ["t_s", "fc", "pulso", "fr", "spo2"]
    assert len(df) == 10
    assert math.isnan(df.loc[2, "fr"]) and math.isnan(df.loc[4, "fc"])
    assert df.loc[3, "fc"] == 92 and df["t_s"].tolist() == list(range(10))


def test_coluna_faltando_e_erro_claro(tmp_path):
    caminho = tmp_path / "x.csv"
    caminho.write_text("Time [s], HR\n0,80\n", encoding="utf-8")
    with pytest.raises(ValueError, match="colunas ausentes"):
        bidmc.ler_numerics(caminho)


def test_baixar_so_o_que_falta(tmp_path, monkeypatch):
    monkeypatch.setattr(baixar_bidmc, "DIR_BIDMC", tmp_path)
    monkeypatch.setattr(baixar_bidmc, "arquivo_bidmc", lambda nr: bidmc.arquivo_bidmc(nr, tmp_path))
    bidmc.arquivo_bidmc(1, tmp_path).write_text(CSV_A_MAO, encoding="utf-8")
    pedidas: list[str] = []

    class Resposta:
        def __init__(self, url: str) -> None:
            self.url = url

        def __enter__(self) -> "Resposta":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return CSV_A_MAO.encode()

    def urlopen(requisicao, timeout):  # noqa: ANN001
        pedidas.append(requisicao.full_url)
        return Resposta(requisicao.full_url)

    monkeypatch.setattr(baixar_bidmc.urllib.request, "urlopen", urlopen)
    assert baixar_bidmc.baixar(2) == 1
    assert pedidas == ["https://physionet.org/files/bidmc/1.0.0/bidmc_csv/bidmc_02_Numerics.csv"]
    assert bidmc.arquivo_bidmc(2, tmp_path).exists()
    assert baixar_bidmc.baixar(2) == 0


@pytest.mark.skipif(not bidmc.arquivo_bidmc(1).exists(), reason="BIDMC não baixado (scripts/baixar_bidmc.py)")
def test_carregar_gravacao_real():
    df = bidmc.carregar(1)
    assert 470 <= len(df) <= 490
    assert list(df.columns) == ["t_s", "fc", "pulso", "fr", "spo2"]
    assert all(df[c].dtype.kind == "f" for c in df.columns)
