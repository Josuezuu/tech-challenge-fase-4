from __future__ import annotations

from datetime import datetime, timedelta

from monitor.alertas.motor import MotorAlertas
from monitor.alertas.redacao import INSTRUCOES, dados_do_alerta, modelo_fixo, redigir_alerta, termo_proibido
from monitor.config import Credenciais
from monitor.eventos import Evento, Fonte, Severidade
from monitor.nuvem.openai_llm import ClienteLLM, Redacao

T0 = datetime(2026, 11, 12, 14, 2, 0)


def _alerta_concordancia():  # noqa: ANN202
    spo2 = Evento("leito-12", T0, Fonte.SINAIS_VITAIS, "spo2_baixa", Severidade.ALTA,
                  "SpO2 90 %, abaixo de 92 % há 5 s", "limiar_clinico/v1", 90.0)
    queda = Evento("leito-12", T0 + timedelta(minutes=2), Fonte.VIDEO, "queda", Severidade.MAXIMA,
                   "Queda detectada ao lado do leito", "queda/v1", 0.9)
    return MotorAlertas().processar_todos([spo2, queda])[-1]


class LLMFalsa:
    def __init__(self, texto: str, origem: str = "real") -> None:
        self.texto, self.origem = texto, origem
        self.chamadas: list[tuple[str, dict]] = []

    def redigir(self, instrucoes, dados, modelo_fixo, max_tokens=400):  # noqa: ANN001, ANN201
        self.chamadas.append((instrucoes, dados))
        return Redacao(texto=self.texto, origem=self.origem)


def test_modelo_fixo_deterministico_cita_fonte_horario_e_fecha():
    alerta = _alerta_concordancia()
    texto = modelo_fixo(dados_do_alerta(alerta))
    assert texto == modelo_fixo(dados_do_alerta(alerta))
    assert texto == (
        "Alerta crítico para leito-12 por concordância entre sinais vitais e vídeo. "
        "Sinais vitais às 14:02:00: SpO2 90 %, abaixo de 92 % há 5 s; vídeo às 14:04:00: "
        "Queda detectada ao lado do leito. Avaliação da equipe necessária."
    )
    assert termo_proibido(texto) is None and len(texto) <= 600
    assert alerta.texto == texto and alerta.texto_origem == "simulado"


def test_modelo_fixo_resume_muitos_eventos():
    dados = dados_do_alerta(_alerta_concordancia())
    dados["eventos"] = dados["eventos"] * 5
    texto = modelo_fixo(dados)
    assert "e mais 6 evento(s)" in texto and len(texto) <= 600


def test_texto_bom_da_llm_e_usado():
    bom = "Alerta crítico: SpO2 90% às 14:02 (sinais vitais) e queda às 14:04 (vídeo). Avaliação da equipe necessária."
    llm = LLMFalsa(bom)
    texto, origem = redigir_alerta(_alerta_concordancia(), llm)
    assert (texto, origem) == (bom, "openai")
    instrucoes, dados = llm.chamadas[0]
    assert instrucoes == INSTRUCOES and "diagnóstico" in INSTRUCOES
    assert set(dados) == {"paciente", "nivel", "regra", "modalidades", "eventos"}  # só dados estruturados


def test_guarda_troca_texto_com_diagnostico_pelo_modelo_fixo():
    alerta = _alerta_concordancia()
    fixo = modelo_fixo(dados_do_alerta(alerta))
    for ruim in [
        "O paciente tem pneumonia e caiu. Avaliação da equipe necessária.",
        "Diagnóstico provável: hipoxemia. Avaliação da equipe necessária.",
        "Administre oxigênio imediatamente.",
        "x" * 601,
        "   ",
    ]:
        assert redigir_alerta(alerta, LLMFalsa(ruim)) == (fixo, "simulado")


def test_texto_gravado_mantem_origem():
    bom = "Alerta crítico às 14:04. Avaliação da equipe necessária."
    assert redigir_alerta(_alerta_concordancia(), LLMFalsa(bom, "gravado")) == (bom, "gravado")


def test_cliente_real_sem_chave_cai_no_modelo_fixo(tmp_path):
    sem_chave = Credenciais(None, None, None, None, None, "gpt-4o-mini")
    llm = ClienteLLM(credenciais=sem_chave, modo="auto", raiz_gravacoes=tmp_path)
    alerta = _alerta_concordancia()
    assert redigir_alerta(alerta, llm) == (modelo_fixo(dados_do_alerta(alerta)), "simulado")
