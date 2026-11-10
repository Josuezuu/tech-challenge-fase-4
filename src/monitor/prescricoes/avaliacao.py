"""Avaliação das regras e da extração sobre prescrições geradas (RF-68).

Detecção: um evento ``prescricao_<tipo>`` no item rotulado com aquele tipo é
acerto; evento de anomalia sem rótulo é falso positivo. O evento INFO de texto
divergente fica fora da detecção e entra na métrica da extração.

Extração: cada texto livre passa pelo Text Analytics for health (ou pela
gravação, ou pelo léxico simulado) e é comparado campo a campo com o estruturado.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from monitor.config import SEMENTE
from monitor.prescricoes.extracao import ExtratorSaude, divergencias, extrair
from monitor.prescricoes.gerador import gerar
from monitor.prescricoes.modelo import TIPOS_ANOMALIA, Extracao, ItemPrescricao
from monitor.prescricoes.regras import avaliar as aplicar_regras

CAMPOS = ("medicamento", "dose", "via", "frequencia")


def extrair_todos(itens: list[ItemPrescricao], cliente: ExtratorSaude) -> dict[str, Extracao]:
    """Extrai cada item; o mesmo texto só vai uma vez ao serviço."""
    por_texto: dict[str, Extracao] = {}
    saida: dict[str, Extracao] = {}
    for item in itens:
        if item.texto_livre not in por_texto:
            por_texto[item.texto_livre] = extrair(item, cliente)
        saida[item.id] = por_texto[item.texto_livre]
    return saida


def _prf(vp: int, fp: int, fn: int) -> dict[str, float]:
    p = vp / (vp + fp) if vp + fp else 0.0
    r = vp / (vp + fn) if vp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return {"vp": vp, "fp": fp, "fn": fn, "precisao": round(p, 3), "recall": round(r, 3), "f1": round(f1, 3)}


def avaliar(
    n_pacientes: int = 8,
    dias: int = 10,
    semente: int = SEMENTE,
    cliente_linguagem: ExtratorSaude | None = None,
) -> dict[str, Any]:
    if cliente_linguagem is None:
        from monitor.nuvem.azure_linguagem import ClienteLinguagem

        cliente_linguagem = ClienteLinguagem()
    itens, rotulos = gerar(n_pacientes, dias, semente)
    extracoes = extrair_todos(itens, cliente_linguagem)
    eventos = aplicar_regras(itens, extracoes)

    esperados = {(r.item_id, r.tipo) for r in rotulos}
    achados = {(e.evidencia["item_id"], e.tipo.removeprefix("prescricao_"))
               for e in eventos if e.tipo != "prescricao_texto_divergente"}
    por_tipo = {
        tipo: _prf(
            vp=len({a for a in achados & esperados if a[1] == tipo}),
            fp=len({a for a in achados - esperados if a[1] == tipo}),
            fn=len({a for a in esperados - achados if a[1] == tipo}),
        )
        for tipo in TIPOS_ANOMALIA
    }
    geral = _prf(len(achados & esperados), len(achados - esperados), len(esperados - achados))

    erros_por_campo: Counter[str] = Counter()
    itens_certos = 0
    for item in itens:
        campos = divergencias(item, extracoes[item.id])
        erros_por_campo.update(campos)
        itens_certos += not campos
    n = len(itens)
    return {
        "pacientes": n_pacientes,
        "dias": dias,
        "semente": semente,
        "itens": n,
        "rotulos": len(rotulos),
        "rotulos_por_tipo": dict(Counter(r.tipo for r in rotulos)),
        "geral": geral,
        "por_tipo": por_tipo,
        "extracao": {
            "acerto_item": round(itens_certos / n, 3) if n else None,
            "acerto_por_campo": {c: round(1 - erros_por_campo[c] / n, 3) if n else None for c in CAMPOS},
            "textos_distintos": len({i.texto_livre for i in itens}),
            "origem": dict(Counter(e.origem for e in extracoes.values())),
            "eventos_texto_divergente": sum(e.tipo == "prescricao_texto_divergente" for e in eventos),
        },
    }
