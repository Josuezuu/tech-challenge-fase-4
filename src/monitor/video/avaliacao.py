"""Avaliação contra anotação manual dos clipes (RF-66).

Anotação (``data/gravacoes/anotacoes.json``)::

    {"V5.mp4": {"cenario": "quarto", "eventos": [{"tipo": "queda", "t_s": 12.0}]}}

Um evento anotado é acerto quando há um detectado do mesmo tipo a até
``tolerancia_s`` segundos (cada detectado casa com um anotado só). Detectado
que não casou é falso positivo. Clipe processado sem anotação é pulado.

Queda só é confirmada depois de ``queda_permanencia_s`` no chão. Quando a
duração do clipe é conhecida e ele acaba antes disso, a queda perdida é marcada
com ``motivo: clipe_acaba_antes_da_confirmacao``: continua contando na
sensibilidade bruta, e fica fora de ``sensibilidade_confirmavel``, que mede só
as quedas que o detector tinha como confirmar.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from monitor.video.config import ConfigQuarto

log = logging.getLogger(__name__)

Detectado = tuple[str, float]  # (tipo, t_s)
SEM_CAUDA = "clipe_acaba_antes_da_confirmacao"


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
    duracoes: Mapping[str, float] | None = None,
    permanencia_s: float = ConfigQuarto().queda_permanencia_s,
) -> dict[str, Any]:
    duracoes = duracoes or {}
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
                           "anotados": [{"tipo": t, "t_s": s} for t, s in esperados],
                           "acertos": acertos, "falsos_positivos": falsos,
                           "perdidos": [_perdido(t, s, duracoes.get(arquivo), permanencia_s) for t, s in perdidos]}
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
    total_fp = sum(c["falsos_positivos"] for c in clipes.values())
    sem_cauda = sum(1 for c in clipes.values() for d in c["perdidos"] if d.get("motivo") == SEM_CAUDA)
    confirmaveis = total_esp - sem_cauda
    sens = round(total_ac / total_esp, 3) if total_esp else None
    prec = round(total_ac / (total_ac + total_fp), 3) if total_ac + total_fp else None
    return {
        "tolerancia_s": tolerancia_s,
        "clipes": clipes,
        "por_tipo": dict(sorted(por_tipo.items())),
        "total": {"esperados": total_esp, "acertos": total_ac, "falsos_positivos": total_fp,
                  "sensibilidade": sens, "precisao": prec, "f1": _f1(sens, prec),
                  "perdidos_sem_cauda": sem_cauda, "permanencia_s": permanencia_s,
                  "sensibilidade_confirmavel": round(total_ac / confirmaveis, 3) if confirmaveis else None},
        "pulados": pulados,
    }


def _perdido(tipo: str, t_s: float, duracao_s: float | None, permanencia_s: float) -> dict[str, Any]:
    perdido: dict[str, Any] = {"tipo": tipo, "t_s": t_s}
    if tipo == "queda" and duracao_s is not None and t_s + permanencia_s > duracao_s + 1e-6:
        perdido["motivo"] = SEM_CAUDA
        perdido["segundos_no_chao_no_clipe"] = round(max(duracao_s - t_s, 0.0), 2)
    return perdido


def _f1(recall: float | None, precisao: float | None) -> float | None:
    """Média harmônica; None quando falta um dos dois."""
    if recall is None or precisao is None:
        return None
    return round(2 * recall * precisao / (recall + precisao), 3) if recall + precisao else 0.0
