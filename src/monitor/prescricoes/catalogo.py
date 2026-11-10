"""Catálogo de medicamentos usado pelo gerador e pelas regras.

ATENÇÃO: valores DIDÁTICOS, plausíveis para um adulto, escolhidos para o
exercício. NÃO são referência clínica: não use para prescrever, conferir ou
ajustar dose de ninguém.

Doses por administração, na unidade padrão do medicamento. ``continuo`` marca
o que não deve parar de uma vez (suspensão abrupta é risco). ``doses_usuais``
são os degraus que o gerador usa na rotina.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Medicamento:
    nome: str
    classe: str
    dose_min: float
    dose_max: float
    unidade: str
    continuo: bool
    vias: tuple[str, ...]
    intervalo_h: float
    doses_usuais: tuple[float, ...]


CATALOGO: dict[str, Medicamento] = {m.nome: m for m in (
    Medicamento("dipirona", "analgesico", 500, 1000, "mg", False, ("IV", "VO"), 6, (500, 750, 1000)),
    Medicamento("paracetamol", "analgesico", 500, 1000, "mg", False, ("VO",), 6, (500, 750, 1000)),
    Medicamento("morfina", "opioide", 2, 10, "mg", False, ("IV", "SC"), 4, (2, 3, 4, 5, 6, 8, 10)),
    Medicamento("tramadol", "opioide", 50, 100, "mg", False, ("IV", "VO"), 8, (50, 75, 100)),
    Medicamento("enoxaparina", "anticoagulante", 20, 80, "mg", True, ("SC",), 24, (20, 40, 60, 80)),
    Medicamento("heparina", "anticoagulante", 2500, 5000, "UI", True, ("SC", "IV"), 8, (2500, 5000)),
    Medicamento("losartana", "anti-hipertensivo", 25, 100, "mg", True, ("VO",), 12, (25, 50, 75, 100)),
    Medicamento("anlodipino", "anti-hipertensivo", 2.5, 10, "mg", True, ("VO",), 24, (2.5, 5, 7.5, 10)),
    Medicamento("metoprolol", "betabloqueador", 25, 100, "mg", True, ("VO",), 12, (25, 50, 75, 100)),
    Medicamento("furosemida", "diuretico", 20, 80, "mg", False, ("IV", "VO"), 12, (20, 40, 60, 80)),
    Medicamento("ceftriaxona", "antibiotico", 1000, 2000, "mg", True, ("IV", "IM"), 12, (1000, 2000)),
    Medicamento("vancomicina", "antibiotico", 500, 1500, "mg", True, ("IV",), 12, (500, 750, 1000, 1250, 1500)),
    Medicamento("insulina", "insulina", 2, 20, "UI", True, ("SC", "IV"), 8, (2, 4, 6, 8, 10, 12)),
    Medicamento("omeprazol", "protetor_gastrico", 20, 40, "mg", False, ("IV", "VO"), 24, (20, 40)),
)}

# Fator para levar uma dose à unidade padrão do medicamento (só entre massas).
FATOR_MASSA = {"mcg": 0.001, "mg": 1.0, "g": 1000.0}


def converter(dose: float, de: str, para: str) -> float | None:
    """Converte dose entre mcg/mg/g; mesma unidade passa direto; UI ↔ mg não tem conversão."""
    if de == para:
        return dose
    if de in FATOR_MASSA and para in FATOR_MASSA:
        return dose * FATOR_MASSA[de] / FATOR_MASSA[para]
    return None
