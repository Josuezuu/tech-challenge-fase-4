"""Números do motor de alertas para o ``resultados.json`` (RF-69)."""

from __future__ import annotations

from collections import Counter
from typing import Any

from monitor.eventos import Alerta


def latencia_ponta_a_ponta(alerta: Alerta) -> float:
    """Segundos entre o primeiro evento da concordância e o alerta crítico.

    É o tempo que a fusão esperou pela segunda modalidade: o alerta sai no
    instante do evento que fechou a concordância.
    """
    return (alerta.instante - min(e.instante for e in alerta.eventos)).total_seconds()


def avaliar(alertas: list[Alerta]) -> dict[str, Any]:
    concordancias = [a for a in alertas if a.regra == "concordancia"]
    latencias = [latencia_ponta_a_ponta(a) for a in concordancias]
    return {
        "alertas": len(alertas),
        "por_nivel": dict(sorted(Counter(a.nivel.name for a in alertas).items())),
        "por_regra": dict(sorted(Counter(a.regra for a in alertas).items())),
        "por_paciente": dict(sorted(Counter(a.paciente_id for a in alertas).items())),
        "texto_origem": dict(sorted(Counter(a.texto_origem for a in alertas).items())),
        "concordancias": len(concordancias),
        "latencia_ponta_a_ponta_s": {
            "primeira": latencias[0] if latencias else None,
            "media": round(sum(latencias) / len(latencias), 1) if latencias else None,
            "maxima": max(latencias) if latencias else None,
        },
    }
