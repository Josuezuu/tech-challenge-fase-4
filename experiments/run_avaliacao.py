"""Avaliação consolidada: roda a avaliação de cada feature e junta tudo em results/resultados.json.

Todas as tabelas do relatório saem deste arquivo. Fonte sem dado vira
``{"status": "sem_dados", "motivo": ...}``; fonte com erro vira ``{"status": "erro", ...}``.

Uso:
    python -m experiments.run_avaliacao [--rapido]
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from monitor.config import CAMINHOS, carregar_credenciais, modo_nuvem

DIR_AVALIACAO = CAMINHOS.resultados / "avaliacao"


def versao_git() -> str | None:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=CAMINHOS.raiz,
                           capture_output=True, text=True, timeout=10, check=True)
        return r.stdout.strip()
    except Exception:  # noqa: BLE001
        return None


def anotacoes_de_video() -> Path | None:
    for caminho in (CAMINHOS.gravacoes / "anotacoes.json", CAMINHOS.brutos / "urfall" / "anotacoes.json"):
        if caminho.exists():
            return caminho
    return None


def rodar(nome: str, executar: Callable[[], int]) -> dict[str, Any]:
    """Roda uma avaliação calando a saída; devolve o JSON que ela gravou ou o motivo da falha."""
    saida = io.StringIO()
    try:
        with contextlib.redirect_stdout(saida):
            codigo = executar()
    except SystemExit as fim:
        codigo = fim.code if isinstance(fim.code, int) else 1
    except Exception as erro:  # noqa: BLE001
        return {"status": "erro", "motivo": f"{type(erro).__name__}: {erro}"}
    arquivo = DIR_AVALIACAO / f"{nome}.json"
    if codigo != 0 or not arquivo.exists():
        return {"status": "sem_dados", "motivo": saida.getvalue().strip()[-300:] or f"código {codigo}"}
    return {"status": "ok", **json.loads(arquivo.read_text(encoding="utf-8"))}


def origens_gravadas() -> dict[str, int]:
    """Quantas respostas reais de cada serviço estão gravadas em docs/execucoes_gravadas."""
    if not CAMINHOS.gravadas.exists():
        return {}
    return {d.name: len(list(d.glob("*.json"))) for d in sorted(CAMINHOS.gravadas.iterdir()) if d.is_dir()}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--rapido", action="store_true", help="sinais em 10 gravações em vez de 53")
    args = p.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    from experiments import run_audio, run_prescricoes, run_sinais, run_video

    for antigo in DIR_AVALIACAO.glob("*.json"):
        antigo.unlink()

    resultados: dict[str, Any] = {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "versao_git": versao_git(),
    }
    n_sinais = "10" if args.rapido else "53"
    resultados["sinais"] = rodar("sinais", lambda: run_sinais.main(["--avaliar", "--n-gravacoes", n_sinais]))
    resultados["prescricoes"] = rodar("prescricoes", lambda: run_prescricoes.main(["--avaliar"]))
    anotacoes = anotacoes_de_video()
    resultados["video"] = (
        rodar("video", lambda: run_video.main(["--avaliar", "--anotacoes", str(anotacoes)]))
        if anotacoes else {"status": "sem_dados", "motivo": "sem data/gravacoes/anotacoes.json nem clipes públicos"}
    )
    if anotacoes is not None and resultados["video"]["status"] == "ok":
        resultados["video"]["anotacoes"] = anotacoes.relative_to(CAMINHOS.raiz).as_posix()
    resultados["audio"] = rodar("audio", lambda: run_audio.main(["--avaliar"]))

    manifesto = CAMINHOS.resultados / "cenario.json"
    resultados["cenario"] = (
        {"status": "ok", **json.loads(manifesto.read_text(encoding="utf-8"))} if manifesto.exists()
        else {"status": "sem_dados", "motivo": "rode python -m experiments.run_cenario"}
    )

    cred = carregar_credenciais()
    modo = modo_nuvem()
    resultados["origens"] = {
        "modo": modo,
        "azure_fala": "real" if cred.tem_azure_fala and modo != "simulado" else "gravado/simulado",
        "azure_linguagem": "real" if cred.tem_azure_linguagem and modo != "simulado" else "gravado/simulado",
        "openai": "real" if cred.tem_openai and modo != "simulado" else "gravado/simulado",
        "respostas_gravadas": origens_gravadas(),
    }

    destino = CAMINHOS.resultados / "resultados.json"
    destino.write_text(json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")
    for nome in ("sinais", "prescricoes", "video", "audio", "cenario"):
        r = resultados[nome]
        print(f"{nome:<12} {r['status']}" + (f" — {r['motivo']}" if r.get("motivo") else ""))
    print(f"→ {destino.relative_to(CAMINHOS.raiz)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
