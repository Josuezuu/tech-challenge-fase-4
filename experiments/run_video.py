"""Vídeo e movimentação: processa um vídeo gravado ou avalia os clipes anotados.

    python -m experiments.run_video --video data/gravacoes/V5.mp4 --cenario quarto \
        --paciente leito-12 --inicio 2026-11-12T14:03:30 [--fps 5]
    python -m experiments.run_video --video data/gravacoes/V1.mp4 --cenario fisioterapia \
        --exercicio elevacao_lateral --paciente fisio-1
    python -m experiments.run_video --avaliar [--anotacoes data/gravacoes/anotacoes.json]

Saídas: ``results/eventos/video_<paciente>.jsonl``, ``results/eventos/movimentacao_<paciente>.jsonl``,
``results/evidencias/video/<nome>_anotado.mp4`` + recortes, ``results/relatorios/<nome>.md``;
com ``--avaliar``, ``results/avaliacao/video.json``.
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime
from pathlib import Path

from monitor.config import CAMINHOS
from monitor.video.avaliacao import avaliar, carregar_anotacoes
from monitor.video.config import EXERCICIOS
from monitor.video.pipeline import ResultadoSessao, processar

INICIO_PADRAO = "2026-11-12T14:00:00"


def _resumo(nome: str, r: ResultadoSessao) -> str:
    linhas = [f"{nome}: {len(r.inferencia.quadros)} quadros ({r.inferencia.origem}, "
              f"{r.inferencia.s_por_quadro:.2f} s/quadro medido)"]
    if r.fisio is not None:
        media = r.fisio.amplitude_media
        linhas.append(f"  repetições {r.fisio.total}, incompletas {r.fisio.incompletas}, "
                      f"amplitude média {'-' if media is None else f'{media:.0f}°'}")
    for e in r.eventos:
        linhas.append(f"  {e.instante:%H:%M:%S} {e.severidade.name:<6} {e.tipo:<24} valor={e.valor}  {e.descricao}")
    if not r.eventos:
        linhas.append("  nenhum evento")
    linhas.append(f"  relatório: {r.relatorio}  (texto {r.texto_origem})")
    if r.video_anotado:
        linhas.append(f"  vídeo anotado: {r.video_anotado}")
    return "\n".join(linhas)


def _avaliar(args: argparse.Namespace) -> None:
    anotacoes = carregar_anotacoes(args.anotacoes)
    pasta = args.anotacoes.parent
    detectados: dict[str, list[tuple[str, float]]] = {}
    inicio = datetime.fromisoformat(args.inicio)
    for arquivo, anotacao in anotacoes.items():
        if args.video and Path(args.video).name != arquivo:
            continue
        caminho = Path(args.video) if args.video else pasta / arquivo
        if not caminho.exists():
            logging.warning("Clipe anotado %s não encontrado em %s", arquivo, pasta)
            continue
        r = processar(caminho, anotacao.get("cenario", "quarto"), caminho.stem, inicio, args.fps,
                      anotacao.get("exercicio", args.exercicio))
        print(_resumo(arquivo, r))
        detectados[arquivo] = [(e.tipo, (e.instante - inicio).total_seconds()) for e in r.eventos]
    resultado = avaliar(anotacoes, detectados)
    destino = CAMINHOS.resultados / "avaliacao" / "video.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(resultado["total"], ensure_ascii=False))
    print(f"avaliação: {destino}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--video", type=Path, help="vídeo gravado (.mp4, .avi)")
    p.add_argument("--cenario", choices=["quarto", "fisioterapia"], default="quarto")
    p.add_argument("--paciente", help="id do paciente (padrão: nome do arquivo)")
    p.add_argument("--inicio", default=INICIO_PADRAO, help="horário do primeiro quadro, ISO (2026-11-12T14:03:30)")
    p.add_argument("--fps", type=float, default=5.0, help="quadros analisados por segundo")
    p.add_argument("--exercicio", choices=sorted(EXERCICIOS), default="elevacao_lateral")
    p.add_argument("--sem-cache", action="store_true", help="roda o modelo mesmo com cache")
    p.add_argument("--avaliar", action="store_true", help="avalia os clipes de --anotacoes")
    p.add_argument("--anotacoes", type=Path, default=CAMINHOS.gravacoes / "anotacoes.json")
    args = p.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    if args.avaliar:
        _avaliar(args)
        return
    if args.video is None:
        p.error("informe --video (ou --avaliar)")
    r = processar(args.video, args.cenario, args.paciente or args.video.stem, datetime.fromisoformat(args.inicio),
                  args.fps, args.exercicio, usar_cache=not args.sem_cache)
    print(_resumo(args.video.name, r))


if __name__ == "__main__":
    main()
