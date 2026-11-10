"""Prescrições: gera a rotina sintética com anomalias, extrai o texto livre e aplica as regras.

Exemplos:
    python -m experiments.run_prescricoes --pacientes 8 --dias 10 --paciente leito-12 --inicio 2026-11-11T08:00:00
    python -m experiments.run_prescricoes --avaliar
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime

from monitor.config import CAMINHOS, SEMENTE
from monitor.eventos import Evento, salvar_jsonl
from monitor.nuvem.azure_linguagem import ClienteLinguagem
from monitor.prescricoes.avaliacao import avaliar, extrair_todos
from monitor.prescricoes.gerador import gerar
from monitor.prescricoes.regras import avaliar as aplicar_regras


def executar(args: argparse.Namespace) -> int:
    itens, rotulos = gerar(args.pacientes, args.dias, args.semente,
                           pacientes=[args.paciente] if args.paciente else None, inicio=args.inicio)
    amostra = CAMINHOS.amostras / "prescricoes.json"
    amostra.parent.mkdir(parents=True, exist_ok=True)
    amostra.write_text(json.dumps({
        "aviso": "Dados sintéticos e catálogo didático; não são referência clínica.",
        "semente": args.semente,
        "itens": [i.to_dict() for i in itens],
        "rotulos": [r.to_dict() for r in rotulos],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    extracoes = extrair_todos(itens, ClienteLinguagem())
    eventos = aplicar_regras(itens, extracoes)
    por_paciente: dict[str, list[Evento]] = defaultdict(list)
    for e in eventos:
        por_paciente[e.paciente_id].append(e)
    for pid in sorted({i.paciente_id for i in itens}):
        salvar_jsonl(CAMINHOS.eventos / f"prescricao_{pid}.jsonl", por_paciente.get(pid, []))
        for e in por_paciente.get(pid, []):
            print(f"{pid:<12} {e.instante:%d/%m %H:%M} {e.severidade.name:<6} {e.tipo:<32} {e.descricao}")
    origens = sorted({x.origem for x in extracoes.values()})
    print(f"{len(itens)} itens, {len(rotulos)} rótulos → {amostra.relative_to(CAMINHOS.raiz)}; "
          f"{len(eventos)} eventos em results/eventos/prescricao_*.jsonl (extração: {', '.join(origens)})")
    return 0


def executar_avaliacao(args: argparse.Namespace) -> int:
    resultado = avaliar(args.pacientes, args.dias, args.semente)
    saida = CAMINHOS.resultados / "avaliacao" / "prescricoes.json"
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    g, x = resultado["geral"], resultado["extracao"]
    print(f"{resultado['itens']} itens, {resultado['rotulos']} rótulos: precisão {g['precisao']}  "
          f"recall {g['recall']}  F1 {g['f1']}")
    print(f"extração: {x['acerto_item']} dos itens com todos os campos certos; origem {x['origem']}")
    print(f"gravado em {saida.relative_to(CAMINHOS.raiz)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--pacientes", type=int, default=8)
    p.add_argument("--dias", type=int, default=10)
    p.add_argument("--paciente", default=None, help="id do primeiro paciente (ex.: leito-12)")
    p.add_argument("--inicio", type=datetime.fromisoformat, default=None, help="primeiro dia, ex.: 2026-11-11T08:00:00")
    p.add_argument("--semente", type=int, default=SEMENTE)
    p.add_argument("--avaliar", action="store_true", help="→ results/avaliacao/prescricoes.json")
    args = p.parse_args(argv)
    return executar_avaliacao(args) if args.avaliar else executar(args)


if __name__ == "__main__":
    sys.exit(main())
