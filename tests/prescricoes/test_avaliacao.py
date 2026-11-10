from __future__ import annotations

from monitor.prescricoes.avaliacao import avaliar


def test_avaliacao_reproduzivel_e_completa(cliente_simulado):
    a = avaliar(4, 8, semente=9, cliente_linguagem=cliente_simulado)
    assert a == avaliar(4, 8, semente=9, cliente_linguagem=cliente_simulado)
    assert a["rotulos"] == 8
    assert a["geral"]["recall"] == 1.0 and a["geral"]["precisao"] == 1.0
    assert set(a["por_tipo"]) == {"dose_excessiva", "fora_da_faixa", "suspensao_abrupta", "duplicidade_classe",
                                  "via_incompativel"}
    assert a["extracao"]["acerto_item"] == 1.0
    assert a["extracao"]["origem"] == {"simulado": a["itens"]}
