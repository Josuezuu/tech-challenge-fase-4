from __future__ import annotations

from datetime import datetime

import pytest

from monitor.prescricoes.catalogo import CATALOGO
from monitor.prescricoes.gerador import gerar
from monitor.prescricoes.modelo import TIPOS_ANOMALIA, ItemPrescricao, RotuloPrescricao


def test_deterministico_e_rotulos_apontam_itens():
    a = gerar(4, 8, semente=11)
    assert a == gerar(4, 8, semente=11)
    assert a != gerar(4, 8, semente=12)
    itens, rotulos = a
    ids = {i.id for i in itens}
    assert len(ids) == len(itens)
    assert rotulos and all(r.item_id in ids and r.tipo in TIPOS_ANOMALIA for r in rotulos)


def test_rotina_plausivel():
    itens, rotulos = gerar(6, 10, semente=3, tipos=())
    assert rotulos == []
    for i in itens:
        med = CATALOGO[i.medicamento]
        assert med.dose_min <= i.dose <= med.dose_max and i.via in med.vias and i.texto_livre
    por_paciente: dict[str, set[str]] = {}
    for i in itens:
        por_paciente.setdefault(i.paciente_id, set()).add(CATALOGO[i.medicamento].classe)
    assert all(len(classes) == 4 for classes in por_paciente.values())  # 4 classes diferentes


def _rotulado(tipo: str) -> list[tuple[ItemPrescricao, list[ItemPrescricao]]]:
    itens, rotulos = gerar(5, 10, semente=7, tipos=(tipo,))
    assert len(rotulos) == 5 and {r.tipo for r in rotulos} == {tipo}
    por_id = {i.id: i for i in itens}
    saida = []
    for r in rotulos:
        alvo = por_id[r.item_id]
        historico = sorted((i for i in itens if i.paciente_id == alvo.paciente_id and i.medicamento == alvo.medicamento
                            and i.instante < alvo.instante), key=lambda i: i.instante)
        saida.append((alvo, historico))
    return saida


def test_dose_excessiva_plantada_triplica():
    for alvo, hist in _rotulado("dose_excessiva"):
        assert alvo.dose >= 3 * hist[-1].dose


def test_fora_da_faixa_plantada_sai_do_catalogo_sem_triplicar():
    for alvo, hist in _rotulado("fora_da_faixa"):
        med = CATALOGO[alvo.medicamento]
        assert alvo.dose > med.dose_max or alvo.dose < med.dose_min
        assert alvo.dose < 3 * hist[-1].dose


def test_suspensao_abrupta_sem_desmame_e_medicamento_some():
    itens, rotulos = gerar(5, 10, semente=7, tipos=("suspensao_abrupta",))
    por_id = {i.id: i for i in itens}
    for r in rotulos:
        alvo = por_id[r.item_id]
        assert alvo.acao == "suspensao" and CATALOGO[alvo.medicamento].continuo
        depois = [i for i in itens if i.paciente_id == alvo.paciente_id and i.medicamento == alvo.medicamento
                  and i.instante > alvo.instante]
        assert depois == []


def test_duplicidade_inicia_outro_da_mesma_classe():
    itens, rotulos = gerar(5, 10, semente=7, tipos=("duplicidade_classe",))
    por_id = {i.id: i for i in itens}
    for r in rotulos:
        alvo = por_id[r.item_id]
        classes = [CATALOGO[i.medicamento].classe for i in itens
                   if i.paciente_id == alvo.paciente_id and i.instante <= alvo.instante]
        assert alvo.acao == "inicio" and classes.count(CATALOGO[alvo.medicamento].classe) >= 2


def test_via_incompativel_fora_do_catalogo():
    for alvo, _ in _rotulado("via_incompativel"):
        assert alvo.via not in CATALOGO[alvo.medicamento].vias


def test_pacientes_e_inicio_configuraveis():
    itens, _ = gerar(2, 3, pacientes=["leito-12"], inicio=datetime(2026, 11, 11, 8, 0))
    assert {i.paciente_id for i in itens} == {"leito-12", "paciente-02"}
    assert min(i.instante for i in itens) == datetime(2026, 11, 11, 8, 0)


def test_ida_e_volta_dos_dicts():
    itens, rotulos = gerar(1, 4)
    assert [ItemPrescricao.from_dict(i.to_dict()) for i in itens] == itens
    assert [RotuloPrescricao.from_dict(r.to_dict()) for r in rotulos] == rotulos


def test_tipo_desconhecido():
    with pytest.raises(ValueError, match="desconhecido"):
        gerar(1, 5, tipos=("alergia",))
