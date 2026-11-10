"""Avaliação contra anotação manual dos clipes (RF-66).

Anotação (``data/gravacoes/anotacoes.json``)::

    {"V5.mp4": {"cenario": "quarto", "eventos": [{"tipo": "queda", "t_s": 12.0}]}}

Um evento anotado é acerto quando há um detectado do mesmo tipo a até
``tolerancia_s`` segundos (cada detectado casa com um anotado só). Detectado
que não casou é falso positivo. Clipe processado sem anotação é pulado.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

Detectado = tuple[str, float]  # (tipo, t_s)


def carregar_anotacoes(caminho: Path) -> dict[str, Any]:
    return json.loads(Path(caminho).read_text(encoding="utf-8"))


def casar(esperados: Sequence[Detectado], detectados: Sequence[Detectado], tolerancia_s: float) -> tuple[int, int, list[Detectado]]:
    """Devolve (acertos, falsos positivos, esperados perdidos)."""
    livres = list(detectados)
    acertos, perdidos = 0, []
    for tipo, t in sorted(esperados, key=lambda e: e[1]):
        candidatos = [d for d in livres if d[0] == tipo and abs(d[1] - t) <= tolerancia_s]
        if candidatos:
            livres.remove(min(candidatos, key=lambda d: abs(d[1] - t)))
            acertos += 1
        else:
            perdidos.append((tipo, t))
    return acertos, len(livres), perdidos


def avaliar(
    anotacoes: Mapping[str, Any] | Path,
    detectados: Mapping[str, Sequence[Detectado]],
    tolerancia_s: float = 2.0,
) -> dict[str, Any]:
    if isinstance(anotacoes, Path):
        anotacoes = carregar_anotacoes(anotacoes)
    por_tipo: dict[str, dict[str, int]] = {}
    clipes: dict[str, Any] = {}
    pulados: list[str] = []
    for arquivo, eventos_detectados in detectados.items():
        if arquivo not in anotacoes:
            log.warning("Clipe %s sem anotação: fora da avaliação", arquivo)
            pulados.append(arquivo)
            continue
        esperados = [(e["tipo"], float(e["t_s"])) for e in anotacoes[arquivo].get("eventos", [])]
        acertos, falsos, perdidos = casar(esperados, eventos_detectados, tolerancia_s)
        clipes[arquivo] = {"cenario": anotacoes[arquivo].get("cenario"), "esperados": len(esperados),
                           "acertos": acertos, "falsos_positivos": falsos,
                           "perdidos": [{"tipo": t, "t_s": s} for t, s in perdidos]}
        for tipo in {t for t, _ in esperados} | {t for t, _ in eventos_detectados}:
            esp = [e for e in esperados if e[0] == tipo]
            det = [d for d in eventos_detectados if d[0] == tipo]
            a, f, _ = casar(esp, det, tolerancia_s)
            soma = por_tipo.setdefault(tipo, {"esperados": 0, "acertos": 0, "falsos_positivos": 0})
            soma["esperados"] += len(esp)
            soma["acertos"] += a
            soma["falsos_positivos"] += f
    for soma in por_tipo.values():
        detectados_tipo = soma["acertos"] + soma["falsos_positivos"]
        soma["sensibilidade"] = round(soma["acertos"] / soma["esperados"], 3) if soma["esperados"] else None
        soma["precisao"] = round(soma["acertos"] / detectados_tipo, 3) if detectados_tipo else None
    total_esp = sum(c["esperados"] for c in clipes.values())
    total_ac = sum(c["acertos"] for c in clipes.values())
    return {
        "tolerancia_s": tolerancia_s,
        "clipes": clipes,
        "por_tipo": dict(sorted(por_tipo.items())),
        "total": {"esperados": total_esp, "acertos": total_ac,
                  "falsos_positivos": sum(c["falsos_positivos"] for c in clipes.values()),
                  "sensibilidade": round(total_ac / total_esp, 3) if total_esp else None},
        "pulados": pulados,
    }
