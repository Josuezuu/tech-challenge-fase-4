"""Dados das prescrições: item estruturado, rótulo de anomalia plantada e extração do texto livre."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Literal

UNIDADES = ("mg", "g", "mcg", "UI", "ml")
VIAS = ("IV", "VO", "SC", "IM", "INAL")
Acao = Literal["inicio", "manutencao", "ajuste", "suspensao"]

TIPOS_ANOMALIA = ("dose_excessiva", "fora_da_faixa", "suspensao_abrupta", "duplicidade_classe", "via_incompativel")


@dataclass(frozen=True)
class ItemPrescricao:
    paciente_id: str
    instante: datetime
    medicamento: str  # minúsculo, sem acento
    dose: float
    unidade: str  # mg | g | mcg | UI | ml
    via: str  # IV | VO | SC | IM | INAL
    intervalo_h: float
    acao: Acao
    texto_livre: str  # ex.: "Dipirona 1 g IV de 6/6h"
    id: str

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["instante"] = self.instante.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ItemPrescricao:
        return cls(**{**d, "instante": datetime.fromisoformat(d["instante"]), "dose": float(d["dose"]),
                      "intervalo_h": float(d["intervalo_h"])})


@dataclass(frozen=True)
class RotuloPrescricao:
    item_id: str
    tipo: str  # um de TIPOS_ANOMALIA
    paciente_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RotuloPrescricao:
        return cls(**d)


@dataclass(frozen=True)
class Extracao:
    """Campos lidos do texto livre pelo Text Analytics for health (ou pelo léxico simulado)."""

    medicamento: str | None
    dose: float | None
    unidade: str | None
    via: str | None
    frequencia_h: float | None
    origem: str  # real | gravado | simulado
