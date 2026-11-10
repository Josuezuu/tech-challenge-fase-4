"""Sinais vitais: reproduz uma gravação do BIDMC como fluxo, ou avalia as 53.

Exemplos:
    python -m experiments.run_sinais --gravacao 1 --paciente leito-12 --inicio 2026-11-12T14:00:00 \\
        --plantar queda_spo2@120 --plantar degrau_fc@300:40
    python -m experiments.run_sinais --avaliar
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime

import pandas as pd

from monitor.config import CAMINHOS, SEMENTE
from monitor.eventos import Evento, salvar_jsonl
from monitor.sinais import bidmc
from monitor.sinais.avaliacao import avaliar
from monitor.sinais.config import AVALIACAO, CONFIG
from monitor.sinais.detectores import MonitorVitais
from monitor.sinais.fluxo import reproduzir
from monitor.sinais.injecao import TIPOS, Especificacao, plantar, pressao_sintetica

DURACAO_PADRAO_S = 60


def especificacao(texto: str) -> Especificacao:
    """``tipo@inicio[:duracao]`` → ``Especificacao`` (ex.: ``queda_spo2@120:60``)."""
    try:
        tipo, resto = texto.split("@")
        inicio, _, duracao = resto.partition(":")
        esp = Especificacao(tipo, float(inicio), float(duracao or DURACAO_PADRAO_S))
    except ValueError as erro:
        raise argparse.ArgumentTypeError(f"use tipo@inicio[:duracao], ex.: queda_spo2@120 ({erro})") from erro
    if esp.tipo not in TIPOS:
        raise argparse.ArgumentTypeError(f"tipo {esp.tipo!r} desconhecido; use {', '.join(TIPOS)}")
    return esp


def gravar_evidencia(df: pd.DataFrame, evento: Evento, inicio: datetime) -> None:
    """CSV com os 120 s ao redor do evento, no caminho que a evidência já aponta."""
    t = (evento.instante - inicio).total_seconds()
    meia = CONFIG.meia_janela_evidencia_s
    trecho = df[(df["t_s"] >= t - meia) & (df["t_s"] <= t + meia)].copy()
    trecho.insert(1, "instante", [(inicio + pd.Timedelta(seconds=s)).isoformat() for s in trecho["t_s"]])
    caminho = CAMINHOS.raiz / evento.evidencia["serie"]
    caminho.parent.mkdir(parents=True, exist_ok=True)
    trecho.to_csv(caminho, index=False)


def executar_fluxo(args: argparse.Namespace) -> int:
    df = bidmc.carregar(args.gravacao)
    rotulos = []
    if args.plantar:
        df, rotulos = plantar(df, args.plantar, args.semente)
    sinteticas: frozenset[str] = frozenset()
    if args.pressao:
        df["pas"] = pressao_sintetica(len(df), args.semente)
        sinteticas = frozenset({"pas"})

    monitor = MonitorVitais(CONFIG, gravacao=bidmc.nome_gravacao(args.gravacao), sinteticas=sinteticas)
    eventos: list[Evento] = []
    for amostra in reproduzir(df, args.paciente, args.inicio, args.velocidade or None):
        novos = monitor.processar(amostra)
        for e in novos:
            print(f"{e.instante:%H:%M:%S} {e.severidade.name:<6} {e.tipo:<12} {e.descricao}")
        eventos.extend(novos)

    for e in eventos:
        gravar_evidencia(df, e, args.inicio)
    saida = CAMINHOS.eventos / f"sinais_vitais_{args.paciente}.jsonl"
    salvar_jsonl(saida, eventos)
    for r in rotulos:
        print(f"rótulo: {r.tipo} {r.inicio_s:g}-{r.fim_s:g} s")
    print(f"{len(eventos)} eventos em {saida.relative_to(CAMINHOS.raiz)}; "
          f"latência média {monitor.latencia_media_ms:.3f} ms por amostra")
    return 0


def executar_avaliacao(args: argparse.Namespace) -> int:
    faltando = [nr for nr in range(1, args.n_gravacoes + 1) if not bidmc.arquivo_bidmc(nr).exists()]
    if faltando:
        print(f"faltam {len(faltando)} gravações; rode: python scripts/baixar_bidmc.py", file=sys.stderr)
        return 1
    gravacoes = {bidmc.nome_gravacao(nr): bidmc.carregar(nr) for nr in range(1, args.n_gravacoes + 1)}
    t0 = time.perf_counter()
    resultado = avaliar(gravacoes, args.n_anomalias, args.semente)
    resultado["tempo_execucao_s"] = round(time.perf_counter() - t0, 1)
    saida = CAMINHOS.resultados / "avaliacao" / "sinais.json"
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    g, s = resultado["geral"], resultado["sem_plantio"]
    print(f"recall {g['recall']}  precisão {g['precisao']}  F1 {g['f1']}  atraso médio {g['atraso_medio_s']} s")
    print(f"sem plantio: {s['alertas_falsos_por_hora']} eventos/h "
          f"({s['alertas_falsos_por_hora_sem_condicao_real']}/h fora das gravações com condição real)")
    print(f"{resultado['tempo_execucao_s']} s; gravado em {saida.relative_to(CAMINHOS.raiz)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--avaliar", action="store_true", help="avalia nas gravações baixadas → results/avaliacao/sinais.json")
    p.add_argument("--gravacao", type=int, default=1, help="número da gravação BIDMC (1..53)")
    p.add_argument("--paciente", default="leito-12")
    p.add_argument("--inicio", type=datetime.fromisoformat, default=datetime(2026, 11, 12, 14, 0, 0))
    p.add_argument("--plantar", type=especificacao, action="append", default=[],
                   help="anomalia tipo@inicio[:duracao], pode repetir")
    p.add_argument("--velocidade", type=float, default=0, help="amostras por segundo de relógio; 0 = sem pausa")
    p.add_argument("--pressao", action="store_true", help="acrescenta PA sistólica sintética (marcada na evidência)")
    p.add_argument("--semente", type=int, default=SEMENTE)
    p.add_argument("--n-anomalias", type=int, default=AVALIACAO.anomalias_por_gravacao)
    p.add_argument("--n-gravacoes", type=int, default=53)
    args = p.parse_args(argv)
    return executar_avaliacao(args) if args.avaliar else executar_fluxo(args)


if __name__ == "__main__":
    sys.exit(main())
