from __future__ import annotations

import pytest

from monitor.eventos import Fonte, Severidade
from monitor.prescricoes.avaliacao import extrair_todos
from monitor.prescricoes.gerador import gerar
from monitor.prescricoes.modelo import TIPOS_ANOMALIA
from monitor.prescricoes.regras import avaliar
from tests.prescricoes.conftest import item


def test_rotina_normal_nao_gera_evento(cliente_simulado):
    itens, _ = gerar(8, 10, semente=21, tipos=())
    assert avaliar(itens, extrair_todos(itens, cliente_simulado)) == []


@pytest.mark.parametrize("tipo", TIPOS_ANOMALIA)
def test_cada_tipo_plantado_sozinho_e_detectado(tipo):
    itens, rotulos = gerar(6, 10, semente=5, tipos=(tipo,))
    eventos = avaliar(itens)
    assert {(e.evidencia["item_id"], e.tipo) for e in eventos} == {(r.item_id, f"prescricao_{tipo}") for r in rotulos}
    assert all(e.fonte == Fonte.PRESCRICAO and e.severidade >= Severidade.ALTA for e in eventos)


def test_dose_excessiva_alta_e_maxima():
    eventos = avaliar([item(0, "morfina", 2), item(1, "morfina", 6, "ajuste")])
    assert [(e.tipo, e.severidade, e.valor) for e in eventos] == [("prescricao_dose_excessiva", Severidade.ALTA, 3.0)]
    assert eventos[0].evidencia["anterior"] == "2 mg"
    maxima = avaliar([item(0, "morfina", 2), item(1, "morfina", 10, "ajuste")])  # 5×
    assert maxima[0].severidade == Severidade.MAXIMA


def test_fora_da_faixa_acima_abaixo_e_maxima():
    acima = avaliar([item(0, "dipirona", 1000), item(1, "dipirona", 1500, "ajuste")])
    assert [(e.tipo, e.severidade) for e in acima] == [("prescricao_fora_da_faixa", Severidade.ALTA)]
    abaixo = avaliar([item(0, "dipirona", 500), item(1, "dipirona", 250, "ajuste")])
    assert "abaixo da mínima" in abaixo[0].descricao
    muito = avaliar([item(0, "tramadol", 100), item(1, "tramadol", 250, "ajuste")])  # > 2× a máxima
    assert (muito[0].tipo, muito[0].severidade) == ("prescricao_fora_da_faixa", Severidade.MAXIMA)


def test_suspensao_com_desmame_nao_alarma_e_sem_desmame_alarma():
    com = [item(0, "metoprolol", 100, "inicio"), item(1, "metoprolol", 100), item(2, "metoprolol", 50, "ajuste"),
           item(3, "metoprolol", 50, "suspensao")]
    assert avaliar(com) == []
    sem = [item(0, "metoprolol", 100, "inicio"), item(1, "metoprolol", 100), item(2, "metoprolol", 100, "suspensao")]
    assert [e.tipo for e in avaliar(sem)] == ["prescricao_suspensao_abrupta"]
    nao_continuo = [item(0, "dipirona", 1000, "inicio"), item(1, "dipirona", 1000, "suspensao")]
    assert avaliar(nao_continuo) == []


def test_duplicidade_so_com_o_outro_ativo():
    dup = [item(0, "morfina", 4, "inicio"), item(1, "tramadol", 50, "inicio")]
    assert [e.tipo for e in avaliar(dup)] == ["prescricao_duplicidade_classe"]
    trocado = [item(0, "morfina", 4, "inicio"), item(1, "morfina", 4, "suspensao"), item(2, "tramadol", 50, "inicio")]
    assert avaliar(trocado) == []
    outro_paciente = [item(0, "morfina", 4, "inicio"), item(1, "tramadol", 50, "inicio", paciente="leito-7")]
    assert avaliar(outro_paciente) == []


def test_via_incompativel():
    eventos = avaliar([item(0, "enoxaparina", 40, "inicio"), item(1, "enoxaparina", 40, via="IV")])
    assert [(e.tipo, e.severidade) for e in eventos] == [("prescricao_via_incompativel", Severidade.ALTA)]


def test_um_evento_por_item_anomalo():
    # 5× a anterior, acima da faixa e via errada no mesmo item: só a primeira regra
    eventos = avaliar([item(0, "tramadol", 50, "inicio"), item(1, "tramadol", 250, "ajuste", via="SC")])
    assert [e.tipo for e in eventos] == ["prescricao_dose_excessiva"]


def test_texto_divergente_vira_info_com_evidencia(cliente_simulado):
    itens = [item(0, "dipirona", 1000, "inicio", via="IV", texto="Dipirona 1 g IV de 6/6h"),
             item(1, "dipirona", 1000, via="IV", texto="Dipirona 500 mg IV de 6/6h")]
    eventos = avaliar(itens, extrair_todos(itens, cliente_simulado))
    assert [(e.tipo, e.severidade) for e in eventos] == [("prescricao_texto_divergente", Severidade.INFO)]
    ev = eventos[0].evidencia
    assert ev["campos"] == "dose" and ev["extracao_origem"] == "simulado" and ev["texto"] == itens[1].texto_livre
    assert set(ev) >= {"item_id", "texto", "anterior", "extracao_origem"}
