"""Contrato comum entre as fontes e o motor de alertas.

Toda análise (vídeo, áudio, sinais vitais, prescrições, movimentação) produz
``Evento``. O motor de alertas consome Eventos e produz ``Alerta``. É esse
contrato que deixa cada fonte ser construída e testada sozinha.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import IntEnum, StrEnum
from pathlib import Path
from typing import Any, Iterable


class Fonte(StrEnum):
    VIDEO = "video"
    MOVIMENTACAO = "movimentacao"
    AUDIO = "audio"
    SINAIS_VITAIS = "sinais_vitais"
    PRESCRICAO = "prescricao"


class Modalidade(StrEnum):
    """Origem física do dado. A fusão conta modalidades, não fontes:
    queda (vídeo) e saída do leito (movimentação) vêm da mesma câmera."""

    VIDEO = "video"
    AUDIO = "audio"
    SINAIS_VITAIS = "sinais_vitais"
    TEXTO_CLINICO = "texto_clinico"


MODALIDADE: dict[Fonte, Modalidade] = {
    Fonte.VIDEO: Modalidade.VIDEO,
    Fonte.MOVIMENTACAO: Modalidade.VIDEO,
    Fonte.AUDIO: Modalidade.AUDIO,
    Fonte.SINAIS_VITAIS: Modalidade.SINAIS_VITAIS,
    Fonte.PRESCRICAO: Modalidade.TEXTO_CLINICO,
}


class Severidade(IntEnum):
    INFO = 1
    ALTA = 2
    MAXIMA = 3


class NivelAlerta(IntEnum):
    INFORMATIVO = 1
    ATENCAO = 2
    CRITICO = 3


@dataclass(frozen=True)
class Evento:
    paciente_id: str
    instante: datetime
    fonte: Fonte
    tipo: str
    severidade: Severidade
    descricao: str
    detector: str
    valor: float | None = None
    evidencia: dict[str, str] = field(default_factory=dict)

    @property
    def modalidade(self) -> Modalidade:
        return MODALIDADE[self.fonte]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["instante"] = self.instante.isoformat()
        d["fonte"] = self.fonte.value
        d["severidade"] = int(self.severidade)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Evento:
        return cls(
            paciente_id=d["paciente_id"],
            instante=datetime.fromisoformat(d["instante"]),
            fonte=Fonte(d["fonte"]),
            tipo=d["tipo"],
            severidade=Severidade(int(d["severidade"])),
            descricao=d["descricao"],
            detector=d["detector"],
            valor=d.get("valor"),
            evidencia=dict(d.get("evidencia") or {}),
        )


@dataclass(frozen=True)
class Alerta:
    id: str
    paciente_id: str
    instante: datetime
    nivel: NivelAlerta
    regra: str
    eventos: tuple[Evento, ...]
    texto: str
    texto_origem: str  # "openai" | "gravado" | "simulado"

    @property
    def modalidades(self) -> list[str]:
        return sorted({e.modalidade.value for e in self.eventos})

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "paciente_id": self.paciente_id,
            "instante": self.instante.isoformat(),
            "nivel": int(self.nivel),
            "nivel_nome": self.nivel.name,
            "regra": self.regra,
            "modalidades": self.modalidades,
            "eventos": [e.to_dict() for e in self.eventos],
            "texto": self.texto,
            "texto_origem": self.texto_origem,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Alerta:
        return cls(
            id=d["id"],
            paciente_id=d["paciente_id"],
            instante=datetime.fromisoformat(d["instante"]),
            nivel=NivelAlerta(int(d["nivel"])),
            regra=d["regra"],
            eventos=tuple(Evento.from_dict(e) for e in d["eventos"]),
            texto=d["texto"],
            texto_origem=d["texto_origem"],
        )


def salvar_jsonl(caminho: Path, itens: Iterable[Evento | Alerta], anexar: bool = False) -> int:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with caminho.open("a" if anexar else "w", encoding="utf-8") as f:
        for item in itens:
            f.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")
            n += 1
    return n


def carregar_eventos(caminho: Path) -> list[Evento]:
    with caminho.open(encoding="utf-8") as f:
        return [Evento.from_dict(json.loads(linha)) for linha in f if linha.strip()]


def carregar_alertas(caminho: Path) -> list[Alerta]:
    with caminho.open(encoding="utf-8") as f:
        return [Alerta.from_dict(json.loads(linha)) for linha in f if linha.strip()]
