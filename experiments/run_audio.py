"""Entrada executável da feature de áudio.

Uma consulta (com referência do paciente para a alteração vocal)::

    python -m experiments.run_audio --audio data/gravacoes/A2.m4a \\
        --referencia data/gravacoes/A1.m4a --paciente leito-12 --inicio 2026-11-13T09:00:00 [--whisper]

→ ``results/eventos/audio_<paciente>.jsonl`` e ``results/audio/<nome>.json``.

Avaliação (sem ``--audio``, usa as amostras sintéticas de ``data/amostras/audio``)::

    python -m experiments.run_audio --avaliar

→ ``results/avaliacao/audio.json``.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from monitor.audio.avaliacao import avaliar
from monitor.audio.conversao import DIR_SAIDA
from monitor.audio.fluxo import Clientes, processar
from monitor.config import CAMINHOS
from monitor.eventos import salvar_jsonl

AMOSTRAS = CAMINHOS.amostras / "audio"
PARES_SINTETICOS = [
    (AMOSTRAS / "sintetico_normal.wav", AMOSTRAS / "sintetico_normal.wav"),
    (AMOSTRAS / "sintetico_normal.wav", AMOSTRAS / "sintetico_alterado.wav"),
    (AMOSTRAS / "sintetico_normal.wav", AMOSTRAS / "sintetico_termos.wav"),
]


def gravar_json(caminho: Path, dados: dict) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Termos críticos e alteração vocal em áudio de consulta.")
    parser.add_argument("--audio", type=Path, help="áudio da consulta (m4a, mp3, mp4, ogg, wav)")
    parser.add_argument("--referencia", type=Path, help="tomada de referência do mesmo paciente")
    parser.add_argument("--paciente", default="leito-12")
    parser.add_argument("--inicio", type=datetime.fromisoformat, default=datetime(2026, 11, 13, 9, 0, 0),
                        help="horário do início da gravação (ISO, ex.: 2026-11-13T09:00:00)")
    parser.add_argument("--whisper", action="store_true", help="transcreve também com o Whisper e calcula o WER")
    parser.add_argument("--avaliar", action="store_true", help="grava results/avaliacao/audio.json")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):  # console do Windows vem em cp1252; capturado não tem reconfigure
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if not args.audio and not args.avaliar:
        parser.error("informe --audio ou --avaliar")

    clientes = Clientes.padrao()
    if args.audio:
        r = processar(args.audio, args.paciente, args.inicio, args.referencia, args.whisper, clientes)
        destino_eventos = CAMINHOS.eventos / f"audio_{args.paciente}.jsonl"
        salvar_jsonl(destino_eventos, r.eventos)
        gravar_json(DIR_SAIDA / f"{args.audio.stem}.json", r.to_dict())
        print(f"transcrição ({r.transcricao.origem}) e análise ({r.analise.origem})")
        for e in r.eventos:
            print(f"  {e.instante:%H:%M:%S} {e.severidade.name:5s} {e.tipo}: {e.descricao}")
        if r.voz:
            z = ", ".join(f"{c.atributo} {c.z:+.2f}" for c in r.voz.atributos)
            print(f"voz: alteração={r.voz.alteracao} | {z}")
        print(f"{len(r.eventos)} eventos → {destino_eventos}")

    if args.avaliar:
        pares = [(args.referencia, args.audio)] if args.audio and args.referencia else PARES_SINTETICOS
        resultado = avaliar(pares, clientes, args.whisper)
        destino = CAMINHOS.resultados / "avaliacao" / "audio.json"
        gravar_json(destino, resultado)
        for p in resultado["pares"]:
            print(f"{p['referencia']} × {p['atual']}: alteração={p['alteracao']} "
                  f"(esperada {p['alteracao_esperada']}) alterados={p['alterados']} termos={p['termos']['achados']}")
        print(f"resumo: {resultado['resumo']} → {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
