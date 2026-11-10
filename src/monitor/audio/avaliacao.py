"""Avaliação da feature de áudio (RF-67).

Para cada par (referência, atual): atributos médios, z de cada atributo,
alteração sim/não (e a esperada), WER por serviço e termos críticos
achados × esperados. O gabarito vem de ``<atual>.esperado.json``
(``{"termos": [...], "alteracao_vocal": true|false}``), quando existe.
"""

from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

from monitor.audio.conversao import DIR_SAIDA
from monitor.audio.fluxo import Clientes, ResultadoAudio, processar, relativo

INICIO_PADRAO = datetime(2026, 11, 13, 9, 0, 0)


def carregar_esperado(audio: Path) -> dict[str, Any] | None:
    caminho = Path(audio).with_suffix(".esperado.json")
    return json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else None


def _arredondar(valor: float | None, casas: int = 4) -> float | None:
    return None if valor is None or math.isnan(valor) else round(valor, casas)


def _termos(resultado: ResultadoAudio, esperado: dict[str, Any] | None) -> dict[str, Any]:
    achados = sorted({e.evidencia["termo"] for e in resultado.eventos if e.tipo == "termo_critico"})
    if esperado is None or "termos" not in esperado:
        return {"achados": achados, "esperados": None}
    esperados = sorted(set(esperado["termos"]))
    return {
        "achados": achados,
        "esperados": esperados,
        "verdadeiros_positivos": len(set(achados) & set(esperados)),
        "falsos_positivos": sorted(set(achados) - set(esperados)),
        "falsos_negativos": sorted(set(esperados) - set(achados)),
    }


def avaliar_par(
    referencia: Path, atual: Path, clientes: Clientes | None = None, whisper: bool = False,
    paciente_id: str = "avaliacao", inicio: datetime = INICIO_PADRAO, dir_saida: Path = DIR_SAIDA,
) -> dict[str, Any]:
    r = processar(atual, paciente_id, inicio, referencia=referencia, whisper=whisper, clientes=clientes,
                  dir_saida=dir_saida)
    assert r.voz is not None and r.atributos_referencia is not None
    esperado = carregar_esperado(atual)
    alteracao_esperada = esperado.get("alteracao_vocal") if esperado else None
    return {
        "referencia": relativo(referencia),
        "atual": relativo(atual),
        "sintetico": bool(esperado and esperado.get("sintetico")),
        "atributos_referencia": {k: _arredondar(v) for k, v in r.atributos_referencia.media().items()},
        "atributos_atual": {k: _arredondar(v) for k, v in r.atributos.media().items()},
        "z": {c.atributo: _arredondar(c.z, 2) for c in r.voz.atributos},
        "alterados": [c.atributo for c in r.voz.alterados],
        "alteracao": r.voz.alteracao,
        "alteracao_esperada": alteracao_esperada,
        "acertou_alteracao": None if alteracao_esperada is None else r.voz.alteracao == alteracao_esperada,
        "wer": {servico: d["wer"] for servico, d in (r.stt or {}).items()},
        "wer_motivo": {servico: d["motivo"] for servico, d in (r.stt or {}).items() if d["motivo"]},
        "termos": _termos(r, esperado),
        "eventos": [f"{e.tipo}:{e.evidencia.get('termo', '')}".rstrip(":") for e in r.eventos],
        "origens": {"transcricao": r.transcricao.origem, "analise": r.analise.origem},
    }


def avaliar(
    pares: Sequence[tuple[Path, Path]], clientes: Clientes | None = None, whisper: bool = False,
    dir_saida: Path = DIR_SAIDA,
) -> dict[str, Any]:
    """Números da feature de áudio para o ``results/resultados.json``."""
    clientes = clientes or Clientes.padrao()
    por_par = [avaliar_par(ref, atual, clientes, whisper, dir_saida=dir_saida) for ref, atual in pares]

    com_gabarito = [p for p in por_par if p["acertou_alteracao"] is not None]
    termos = [p["termos"] for p in por_par if p["termos"]["esperados"] is not None]
    vp = sum(t["verdadeiros_positivos"] for t in termos)
    fp = sum(len(t["falsos_positivos"]) for t in termos)
    fn = sum(len(t["falsos_negativos"]) for t in termos)
    return {
        "pares": por_par,
        "resumo": {
            "n_pares": len(por_par),
            "acertos_alteracao": sum(p["acertou_alteracao"] for p in com_gabarito),
            "pares_com_gabarito": len(com_gabarito),
            "termos_vp": vp,
            "termos_fp": fp,
            "termos_fn": fn,
            "termos_precisao": round(vp / (vp + fp), 3) if vp + fp else None,
            "termos_recall": round(vp / (vp + fn), 3) if vp + fn else None,
            "so_amostras_sinteticas": all(p["sintetico"] for p in por_par),
        },
    }
