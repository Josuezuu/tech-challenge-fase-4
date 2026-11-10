"""O que a inferência entrega por quadro: pessoas (esqueleto) e objetos (leito, cadeira).

Fica separado de ``inferencia.py`` para que os módulos puros (geometria,
paciente, fisioterapia, quarto) usem estes tipos sem importar o YOLO.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

Caixa = tuple[float, float, float, float]  # x1, y1, x2, y2 em pixels
Poligono = tuple[tuple[float, float], ...]  # vértices em pixels (zona do leito)


@dataclass(frozen=True)
class Pessoa:
    pontos: np.ndarray  # (17, 2) em pixels; NaN onde a confiança do ponto é baixa
    confiancas: np.ndarray  # (17,)
    caixa: Caixa
    conf: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "pontos": [[_num(x), _num(y)] for x, y in self.pontos],
            "confiancas": [round(float(c), 3) for c in self.confiancas],
            "caixa": [round(float(v), 1) for v in self.caixa],
            "conf": round(float(self.conf), 3),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Pessoa:
        pontos = np.array([[np.nan if v is None else v for v in p] for p in d["pontos"]], dtype=float)
        return cls(pontos, np.array(d["confiancas"], dtype=float), tuple(d["caixa"]), float(d["conf"]))


@dataclass(frozen=True)
class Objeto:
    classe: str  # nome COCO: "bed", "chair"
    caixa: Caixa
    conf: float

    def to_dict(self) -> dict[str, Any]:
        return {"classe": self.classe, "caixa": [round(float(v), 1) for v in self.caixa],
                "conf": round(float(self.conf), 3)}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Objeto:
        return cls(d["classe"], tuple(d["caixa"]), float(d["conf"]))


@dataclass(frozen=True)
class QuadroAnalisado:
    t_s: float  # segundos desde o início do vídeo
    pessoas: list[Pessoa]
    objetos: list[Objeto]

    def to_dict(self) -> dict[str, Any]:
        return {"t_s": round(self.t_s, 4), "pessoas": [p.to_dict() for p in self.pessoas],
                "objetos": [o.to_dict() for o in self.objetos]}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> QuadroAnalisado:
        return cls(float(d["t_s"]), [Pessoa.from_dict(p) for p in d["pessoas"]],
                   [Objeto.from_dict(o) for o in d["objetos"]])


def _num(v: float) -> float | None:
    return None if np.isnan(v) else round(float(v), 1)
