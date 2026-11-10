from __future__ import annotations

from datetime import datetime, timedelta

from monitor.alertas.saida import gravar_alertas, processar_arquivos
from monitor.eventos import Evento, Fonte, Severidade, carregar_alertas, salvar_jsonl

T0 = datetime(2026, 11, 12, 14, 2, 0)


def test_le_varios_arquivos_e_ida_e_volta_preserva_evidencia(tmp_path):
    spo2 = Evento("leito-12", T0, Fonte.SINAIS_VITAIS, "spo2_baixa", Severidade.ALTA, "SpO2 90 %",
                  "limiar_clinico/v1", 90.0, {"gravacao": "bidmc_01", "janela": "60-180 s",
                                              "serie": "results/evidencias/sinais/leito-12_spo2_baixa_120.csv"})
    queda = Evento("leito-12", T0 + timedelta(minutes=2), Fonte.VIDEO, "queda", Severidade.MAXIMA, "Queda",
                   "queda/v1", 0.91, {"quadro": "results/evidencias/video/q.jpg"})
    salvar_jsonl(tmp_path / "eventos" / "video_leito-12.jsonl", [queda])
    salvar_jsonl(tmp_path / "eventos" / "sinais_vitais_leito-12.jsonl", [spo2])

    alertas = processar_arquivos(sorted((tmp_path / "eventos").glob("*.jsonl")))
    assert [a.regra for a in alertas] == ["severidade_alta", "concordancia"]
    assert alertas[1].eventos[0].evidencia == spo2.evidencia
    assert alertas[1].eventos[1].evidencia == queda.evidencia

    caminho = tmp_path / "alertas.jsonl"
    assert gravar_alertas(alertas, caminho) == 2
    assert carregar_alertas(caminho) == alertas
