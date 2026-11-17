"""Gera a versão "cansada" de uma consulta gravada (controle positivo da alteração vocal).

    python -m experiments.gerar_voz_cansada --audio data/amostras/audio/paciente_8830.m4a --nivel moderada

→ ``data/amostras/audio/<nome>_cansada.wav`` e o gabarito ``<nome>_cansada.esperado.json``
(``alteracao_vocal: true``). As palavras vêm da transcrição da gravação original
(gravada em ``docs/execucoes_gravadas``; em ``simulado`` não chama a rede).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import soundfile as sf

from monitor.audio.cansaco import NIVEIS, cansar
from monitor.audio.conversao import DIR_SAIDA, para_wav
from monitor.audio.fluxo import Clientes, relativo
from monitor.audio.transcricao import transcrever


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Voz cansada a partir de uma gravação real.")
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--nivel", choices=sorted(NIVEIS), default="moderada")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    wav = para_wav(args.audio, DIR_SAIDA / f"{args.audio.stem}.wav")
    transcricao = transcrever(wav, Clientes.padrao().fala)
    sinal, taxa = sf.read(str(wav), dtype="float64", always_2d=True)
    alterado, _ = cansar(sinal.mean(axis=1), taxa, transcricao.palavras, args.nivel)

    destino = args.audio.with_name(f"{args.audio.stem}_cansada.wav")
    sf.write(destino, alterado, taxa, subtype="PCM_16")
    n = NIVEIS[args.nivel]
    gabarito = {
        "sintetico": False,
        "manipulada": {
            "origem": relativo(args.audio),
            "nivel": args.nivel,
            "lentidao": n.lentidao,
            "pausa_a_cada_palavras": n.pausa_a_cada,
            "pausa_s": n.pausa_s,
            "ganho_db": n.ganho_db,
            "sopro_db": n.sopro_db,
        },
        "alteracao_vocal": True,
    }
    destino.with_suffix(".esperado.json").write_text(json.dumps(gabarito, ensure_ascii=False, indent=2) + "\n",
                                                     encoding="utf-8")
    print(f"{relativo(destino)} ({len(alterado) / taxa:.1f} s, nível {args.nivel}; transcrição {transcricao.origem})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
