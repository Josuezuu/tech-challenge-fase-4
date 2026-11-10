"""Regras sobre o histórico de prescrições (RF-52). Sem E/S: itens (e extrações) entram, Eventos saem.

O histórico de cada paciente é percorrido em ordem de instante, guardando o
último item de cada medicamento e quais estão ativos (começaram e não foram
suspensos). Cada item anômalo gera **um** evento, pela primeira regra que
casar, nesta ordem:

1. ``dose_excessiva``: dose ≥ 3× a anterior do mesmo medicamento;
2. ``fora_da_faixa``: dose abaixo de ``dose_min`` ou acima de ``dose_max`` do catálogo;
3. ``via_incompativel``: via fora das vias do catálogo;
4. ``suspensao_abrupta``: contínuo suspenso sem redução de dose no item anterior;
5. ``duplicidade_classe``: começa um medicamento com outro da mesma classe ativo.

À parte, se a extração do texto livre discordar do estruturado, sai um evento
INFO ``prescricao_texto_divergente`` para o mesmo item.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from monitor.eventos import Evento, Fonte, Severidade
from monitor.prescricoes.catalogo import CATALOGO, Medicamento, converter
from monitor.prescricoes.config import REGRAS, ConfigRegras
from monitor.prescricoes.extracao import divergencias
from monitor.prescricoes.modelo import Extracao, ItemPrescricao

DETECTOR = "regras_prescricao/v1"


def _numero(x: float) -> str:
    return f"{x:g}".replace(".", ",")


def _dose_padrao(item: ItemPrescricao, med: Medicamento) -> float | None:
    return converter(item.dose, item.unidade, med.unidade)


def classificar(
    item: ItemPrescricao,
    historico_med: list[ItemPrescricao],
    ativos: dict[str, ItemPrescricao],
    config: ConfigRegras = REGRAS,
) -> tuple[str, Severidade, str, float | None] | None:
    """Devolve ``(tipo, severidade, descrição, valor)`` da primeira regra que casar, ou ``None``.

    ``historico_med``: itens anteriores do mesmo medicamento, em ordem.
    ``ativos``: medicamento → último item, para os que estão ativos agora.
    """
    med = CATALOGO.get(item.medicamento)
    if med is None:
        return None  # fora do catálogo: sem faixa para comparar
    anterior = historico_med[-1] if historico_med else None
    dose = _dose_padrao(item, med)

    if item.acao != "suspensao" and dose is not None:
        dose_ant = _dose_padrao(anterior, med) if anterior and anterior.acao != "suspensao" else None
        muito_acima = dose > config.fator_maxima_dose_max * med.dose_max
        if dose_ant and dose >= config.fator_dose_excessiva * dose_ant:
            fator = dose / dose_ant
            sev = Severidade.MAXIMA if fator >= config.fator_maxima_anterior or muito_acima else Severidade.ALTA
            desc = (f"Dose de {item.medicamento} subiu de {_numero(dose_ant)} para {_numero(dose)} {med.unidade} "
                    f"({_numero(round(fator, 1))}× a anterior)")
            return "dose_excessiva", sev, desc, round(fator, 2)
        if dose < med.dose_min or dose > med.dose_max:
            sentido = "acima da máxima" if dose > med.dose_max else "abaixo da mínima"
            sev = Severidade.MAXIMA if muito_acima else Severidade.ALTA
            desc = (f"Dose de {item.medicamento} {_numero(dose)} {med.unidade} {sentido} do catálogo didático "
                    f"({_numero(med.dose_min)}–{_numero(med.dose_max)} {med.unidade})")
            return "fora_da_faixa", sev, desc, dose

    if item.via not in med.vias:
        desc = f"Via {item.via} para {item.medicamento}, fora das vias do catálogo ({', '.join(med.vias)})"
        return "via_incompativel", Severidade.ALTA, desc, None

    if item.acao == "suspensao" and med.continuo:
        penultimo = historico_med[-2] if len(historico_med) >= 2 else None
        houve_desmame = anterior is not None and penultimo is not None and anterior.dose < penultimo.dose
        if not houve_desmame:
            desc = f"Suspensão de {item.medicamento} (uso contínuo) sem redução prévia da dose"
            return "suspensao_abrupta", Severidade.ALTA, desc, item.dose

    if item.medicamento not in ativos and item.acao != "suspensao":
        mesma_classe = sorted(n for n in ativos
                              if n != item.medicamento and n in CATALOGO and CATALOGO[n].classe == med.classe)
        if mesma_classe:
            desc = (f"Início de {item.medicamento} com {', '.join(mesma_classe)} em uso: dois medicamentos "
                    f"da mesma classe ({med.classe})")
            return "duplicidade_classe", Severidade.ALTA, desc, None
    return None


def avaliar(
    historico: Iterable[ItemPrescricao],
    extracoes: dict[str, Extracao] | None = None,
    config: ConfigRegras = REGRAS,
) -> list[Evento]:
    """Eventos de todas as regras, para um ou vários pacientes. ``extracoes``: id do item → extração."""
    extracoes = extracoes or {}
    por_paciente: dict[str, list[ItemPrescricao]] = defaultdict(list)
    for item in historico:
        por_paciente[item.paciente_id].append(item)

    eventos: list[Evento] = []
    for pid in sorted(por_paciente):
        historicos: dict[str, list[ItemPrescricao]] = defaultdict(list)
        ativos: dict[str, ItemPrescricao] = {}
        for item in sorted(por_paciente[pid], key=lambda i: (i.instante, i.id)):
            anteriores = historicos[item.medicamento]
            extracao = extracoes.get(item.id)
            anterior = anteriores[-1] if anteriores else None
            evidencia = {
                "item_id": item.id,
                "texto": item.texto_livre,
                "anterior": f"{_numero(anterior.dose)} {anterior.unidade}" if anterior else "sem item anterior",
                "extracao_origem": extracao.origem if extracao else "nao_extraido",
            }
            achado = classificar(item, anteriores, ativos, config)
            if achado:
                tipo, sev, desc, valor = achado
                eventos.append(Evento(pid, item.instante, Fonte.PRESCRICAO, f"prescricao_{tipo}", sev, desc,
                                      DETECTOR, valor, evidencia))
            if extracao is not None:
                campos = divergencias(item, extracao, config.tolerancia_dose)
                if campos:
                    desc = f"Texto livre difere do campo estruturado em: {', '.join(campos)}"
                    eventos.append(Evento(pid, item.instante, Fonte.PRESCRICAO, "prescricao_texto_divergente",
                                          Severidade.INFO, desc, DETECTOR, float(len(campos)),
                                          {**evidencia, "campos": ", ".join(campos)}))
            anteriores.append(item)
            if item.acao == "suspensao":
                ativos.pop(item.medicamento, None)
            else:
                ativos[item.medicamento] = item
    return eventos
