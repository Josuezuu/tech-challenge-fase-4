"""Baixa as Numerics (1 Hz) do BIDMC PPG and Respiration 1.0.0 (PhysioNet, acesso aberto).

Uso: ``python scripts/baixar_bidmc.py [--n 53]``. Só baixa o que ainda não
existe em ``data/raw/bidmc/``.
"""

from __future__ import annotations

import argparse
import sys
import urllib.request

from monitor.sinais.bidmc import DIR_BIDMC, URL_BIDMC, arquivo_bidmc

TOTAL_GRAVACOES = 53


def baixar(n: int = TOTAL_GRAVACOES) -> int:
    """Baixa as gravações 1..n que faltam; devolve quantas baixou."""
    DIR_BIDMC.mkdir(parents=True, exist_ok=True)
    baixadas = 0
    for nr in range(1, n + 1):
        destino = arquivo_bidmc(nr)
        if destino.exists() and destino.stat().st_size > 0:
            continue
        url = URL_BIDMC.format(nr=nr)
        requisicao = urllib.request.Request(url, headers={"User-Agent": "monitor-multimodal/0.1"})
        with urllib.request.urlopen(requisicao, timeout=60) as resposta:
            conteudo = resposta.read()
        temporario = destino.with_suffix(".parcial")
        temporario.write_bytes(conteudo)
        temporario.replace(destino)  # só vira arquivo final depois de baixado inteiro
        baixadas += 1
        print(f"baixado {destino.name} ({len(conteudo)} bytes)")
    return baixadas


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=TOTAL_GRAVACOES, help="baixa as gravações 1..n (padrão 53)")
    args = parser.parse_args(argv)
    if not 1 <= args.n <= TOTAL_GRAVACOES:
        parser.error(f"--n deve estar entre 1 e {TOTAL_GRAVACOES}")
    baixadas = baixar(args.n)
    print(f"{baixadas} baixadas; {args.n - baixadas} já existiam em {DIR_BIDMC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
