"""Alertas: lê os eventos de todas as fontes, aplica a fusão e grava ``results/alertas.jsonl``.

Exemplo:
    python -m experiments.run_alertas
    python -m experiments.run_alertas --eventos results/eventos/sinais_vitais_leito-12.jsonl results/eventos/video_leito-12.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from monitor.alertas.avaliacao import avaliar
from monitor.alertas.motor import MotorAlertas
from monitor.alertas.saida import gravar_alertas, processar_arquivos
from monitor.config import CAMINHOS
from monitor.nuvem.openai_llm import ClienteLLM


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--eventos", type=Path, nargs="*", default=None,
                   help="arquivos de eventos (padrão: results/eventos/*.jsonl)")
    p.add_argument("--saida", type=Path, default=CAMINHOS.resultados / "alertas.jsonl")
    p.add_argument("--sem-llm", action="store_true", help="usa só o modelo fixo de texto, sem chamar a OpenAI")
    args = p.parse_args(argv)

    arquivos = args.eventos if args.eventos else sorted(CAMINHOS.eventos.glob("*.jsonl"))
    if not arquivos:
        print(f"nenhum arquivo de eventos em {CAMINHOS.eventos}", file=sys.stderr)
        return 1
    motor = MotorAlertas(cliente_llm=None if args.sem_llm else ClienteLLM())
    alertas = processar_arquivos(arquivos, motor)
    gravar_alertas(alertas, args.saida)

    print(f"{len(arquivos)} arquivo(s) de eventos → {len(alertas)} alertas em {args.saida}")
    contagem = Counter((a.paciente_id, a.nivel.name) for a in alertas)
    for (paciente, nivel), n in sorted(contagem.items()):
        print(f"  {paciente:<12} {nivel:<11} {n}")
    for a in alertas:
        if a.regra == "concordancia":
            print(f"  CRÍTICO {a.paciente_id} {a.instante:%H:%M:%S} [{', '.join(a.modalidades)}] {a.texto}")

    resultado = avaliar(alertas)
    destino = CAMINHOS.resultados / "avaliacao" / "alertas.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"latência ponta a ponta: {resultado['latencia_ponta_a_ponta_s']} → {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
