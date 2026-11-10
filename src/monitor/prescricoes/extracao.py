"""Extração de medicamento, dose, via e frequência do texto livre (RF-51).

O texto vai para o Text Analytics for health (``ClienteLinguagem.entidades_saude``),
que devolve entidades ``MedicationName``, ``Dosage``, ``MedicationRoute`` e
``Frequency``. Aqui as entidades viram números: "1 g" → (1, "g"),
"de 6/6h" / "8 em 8 horas" / "2x ao dia" → horas entre doses. Se o serviço
não marcar a frequência (o léxico simulado não conhece "8 em 8 horas"), a
mesma conversão roda sobre o texto inteiro.
"""

from __future__ import annotations

import re
from typing import Protocol

from monitor.nuvem.azure_linguagem import EntidadeSaude
from monitor.nuvem.gravacao import Origem
from monitor.nuvem.lexico import VIAS as VIAS_LEXICO
from monitor.nuvem.lexico import normalizar
from monitor.prescricoes.catalogo import CATALOGO, converter
from monitor.prescricoes.modelo import VIAS, Extracao, ItemPrescricao


class ExtratorSaude(Protocol):
    def entidades_saude(self, texto: str, idioma: str = "pt") -> tuple[tuple[EntidadeSaude, ...], Origem]: ...


NUMERO_POR_EXTENSO = {"um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "seis": 6}
UNIDADE = {"mg": "mg", "g": "g", "mcg": "mcg", "ml": "ml", "ui": "UI"}

RE_DOSE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(mcg|mg|ml|ui|g)\b")
RE_BARRA = re.compile(r"(\d+)\s*/\s*(\d+)\s*h")  # 6/6h, de 12/12 h
RE_EM = re.compile(r"(\d+)\s*em\s*(\d+)\s*h")  # 8 em 8 horas
RE_CADA = re.compile(r"a\s+cada\s+(\d+(?:[.,]\d+)?)\s*h")  # a cada 8 horas
RE_VEZES = re.compile(r"(\d+|um|uma|dois|duas|tres|quatro|seis)\s*(?:x|vezes|vez)\s*(?:ao|por)\s*dia")


def _float(texto: str) -> float:
    return float(texto.replace(",", "."))


def horas_da_frequencia(texto: str) -> float | None:
    """Horas entre doses: "6/6h" → 6, "8 em 8 horas" → 8, "a cada 12 horas" → 12, "2x ao dia" → 12."""
    t = normalizar(texto)
    if m := RE_BARRA.search(t):
        return _float(m.group(2))
    if m := RE_EM.search(t):
        return _float(m.group(2))
    if m := RE_CADA.search(t):
        return _float(m.group(1))
    if m := RE_VEZES.search(t):
        vezes = NUMERO_POR_EXTENSO.get(m.group(1)) or int(m.group(1))
        return 24 / vezes
    return None


def dose_do_texto(texto: str) -> tuple[float, str] | None:
    """"1 g" → (1.0, "g"); "2,5mg" → (2.5, "mg"); "5000 UI" → (5000.0, "UI")."""
    m = RE_DOSE.search(normalizar(texto))
    return (_float(m.group(1)), UNIDADE[m.group(2)]) if m else None


def _medicamento(entidade: EntidadeSaude) -> str:
    norm = normalizar(entidade.texto)
    for nome in CATALOGO:
        if nome in norm:
            return nome
    return normalizar(entidade.normalizado or entidade.texto).strip()


def _via(entidade: EntidadeSaude) -> str | None:
    norm = normalizar(entidade.texto).strip()
    if norm in VIAS_LEXICO:
        return VIAS_LEXICO[norm]
    if entidade.normalizado and entidade.normalizado.upper() in VIAS:
        return entidade.normalizado.upper()
    return None


def extrair_texto(texto: str, cliente: ExtratorSaude) -> Extracao:
    entidades, origem = cliente.entidades_saude(texto)

    def primeira(categoria: str) -> EntidadeSaude | None:
        return next((e for e in entidades if e.categoria == categoria), None)

    nome = primeira("MedicationName")
    dosagem = primeira("Dosage")
    rota = primeira("MedicationRoute")
    frequencia = primeira("Frequency")
    dose = (dose_do_texto(dosagem.texto) if dosagem else None) or dose_do_texto(texto)
    horas = (horas_da_frequencia(frequencia.texto) if frequencia else None) or horas_da_frequencia(texto)
    return Extracao(
        medicamento=_medicamento(nome) if nome else None,
        dose=dose[0] if dose else None,
        unidade=dose[1] if dose else None,
        via=_via(rota) if rota else None,
        frequencia_h=horas,
        origem=origem,
    )


def extrair(item: ItemPrescricao, cliente: ExtratorSaude) -> Extracao:
    return extrair_texto(item.texto_livre, cliente)


def divergencias(item: ItemPrescricao, extracao: Extracao, tolerancia: float = 1e-6) -> list[str]:
    """Campos em que o texto livre diz outra coisa que o estruturado (dose comparada na mesma unidade)."""
    campos: list[str] = []
    if extracao.medicamento != item.medicamento:
        campos.append("medicamento")
    dose = None
    if extracao.dose is not None and extracao.unidade is not None:
        dose = converter(extracao.dose, extracao.unidade, item.unidade)
    if dose is None or abs(dose - item.dose) > tolerancia * max(1.0, item.dose):
        campos.append("dose")
    if extracao.via != item.via:
        campos.append("via")
    if extracao.frequencia_h is None or abs(extracao.frequencia_h - item.intervalo_h) > 1e-6:
        campos.append("frequencia")
    return campos
