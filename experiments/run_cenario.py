"""Cenário de ponta a ponta: todas as fontes de todos os pacientes → motor de alertas → painel.

Uso:
    python -m experiments.run_cenario [--cenario data/cenario.json] [--sem-llm]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from monitor.cenario import CENARIO_PADRAO, carregar, executar
from monitor.config import CAMINHOS, Credenciais
from monitor.eventos import carregar_alertas
from monitor.nuvem.openai_llm import ClienteLLM


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cenario", type=Path, default=CENARIO_PADRAO)
    p.add_argument("--sem-llm", action="store_true", help="texto dos alertas só pelo modelo fixo")
    args = p.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):  # console do Windows usa cp1252 e quebra os acentos
        sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    cliente = ClienteLLM(Credenciais(None, None, None, None, None, "-"), "simulado") if args.sem_llm else None
    manifesto = executar(carregar(args.cenario), cliente_llm=cliente)

    for pid, dados in manifesto["pacientes"].items():
        fontes = ", ".join(f"{nome} {f['status']} ({f['eventos']} ev.)" for nome, f in dados["fontes"].items())
        print(f"{pid}: {fontes}")
    print()
    for a in carregar_alertas(CAMINHOS.resultados / "alertas.jsonl"):
        print(f"{a.instante:%d/%m %H:%M:%S} {a.paciente_id:<9} {a.nivel.name:<11} {a.regra:<18} "
              f"[{', '.join(a.modalidades)}] {a.texto[:90]}")
    print()
    print(f"{manifesto['eventos']} eventos; alertas {manifesto['alertas']}; concordâncias {manifesto['concordancias']}")
    c = manifesto["primeira_concordancia"]
    if c:
        print(f"primeira concordância: {c['paciente_id']} {c['instante']} ({', '.join(c['modalidades'])}), "
              f"{c['segundos_desde_primeiro_evento']:.0f} s depois do primeiro evento que ela reúne")
    print("manifesto: results/cenario.json · painel: streamlit run app/painel.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
