"""Baixa poucos clipes do UR Fall Detection Dataset e monta a anotação deles.

Fonte: http://fenix.ur.edu.pl/~mkepski/ds/uf.html (Kwolek e Kępski, Univ. de Rzeszów).
Licença: Creative Commons Atribuição-NãoComercial-CompartilhaIgual 4.0 (CC BY-NC-SA 4.0),
para uso acadêmico não comercial. Download direto, sem cadastro (conferido em 10/11/2026).
Citação pedida: B. Kwolek, M. Kępski, "Human fall detection on embedded platform using depth
maps and wireless accelerometer", Computer Methods and Programs in Biomedicine 117(3), 2014.

Só a câmera frontal (cam0, RGB, 30 fps, ~1,3 MB por clipe). O conjunto tem 30 quedas e
40 atividades do dia a dia; aqui baixamos poucos (pouco disco). A anotação vem do CSV
oficial de rótulos por quadro (-1 não deitado, 0 caindo, 1 deitado no chão): o instante
da queda é o primeiro quadro com rótulo 1.

    python scripts/baixar_quedas.py [--clipes fall-01 fall-02 adl-01]
    python -m experiments.run_video --avaliar --anotacoes data/raw/urfall/anotacoes.json
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import urllib.request
from pathlib import Path

BASE = "http://fenix.ur.edu.pl/~mkepski/ds/data/"
CSV_QUEDAS = "urfall-cam0-falls.csv"
FPS = 30.0
DESTINO = Path(__file__).resolve().parents[1] / "data" / "raw" / "urfall"


def baixar(nome: str, destino: Path) -> Path:
    caminho = destino / nome
    if not caminho.exists():
        with urllib.request.urlopen(BASE + nome, timeout=60) as resposta:
            caminho.write_bytes(resposta.read())
    return caminho


def instante_da_queda(rotulos_csv: str, clipe: str) -> float | None:
    """Primeiro quadro deitado no chão (rótulo 1) do clipe, em segundos."""
    for linha in csv.reader(io.StringIO(rotulos_csv)):
        if len(linha) >= 3 and linha[0] == clipe and linha[2].strip() == "1":
            return (int(linha[1]) - 1) / FPS
    return None


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--clipes", nargs="+", default=["fall-01", "fall-02", "adl-01"])
    args = p.parse_args()
    DESTINO.mkdir(parents=True, exist_ok=True)
    rotulos = baixar(CSV_QUEDAS, DESTINO).read_text(encoding="utf-8")
    anotacoes = {}
    for clipe in args.clipes:
        video = baixar(f"{clipe}-cam0.mp4", DESTINO)
        eventos = []
        if clipe.startswith("fall"):
            t = instante_da_queda(rotulos, clipe)
            if t is not None:
                eventos.append({"tipo": "queda", "t_s": round(t, 2)})
        anotacoes[video.name] = {"cenario": "quarto", "eventos": eventos}
        print(f"{video.name}: {video.stat().st_size / 1e6:.1f} MB, eventos anotados {eventos}")
    (DESTINO / "anotacoes.json").write_text(json.dumps(anotacoes, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"anotação: {DESTINO / 'anotacoes.json'}")


if __name__ == "__main__":
    main()
