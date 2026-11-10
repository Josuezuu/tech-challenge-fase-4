"""Gravação de respostas reais e decisão real × gravado × simulado.

Toda chamada real bem-sucedida grava a resposta em
``docs/execucoes_gravadas/<servico>/<chave>.json``. Sem chave, o cliente
devolve a resposta gravada da mesma entrada; sem gravação, cai na heurística
local. Assim o projeto roda inteiro para quem não tem conta no Azure, e a
origem de cada resultado fica explícita.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Callable, Literal

from monitor.config import CAMINHOS, ModoNuvem

log = logging.getLogger(__name__)

Origem = Literal["real", "gravado", "simulado"]


def chave_de(*partes: bytes | str) -> str:
    h = hashlib.sha256()
    for p in partes:
        h.update(p if isinstance(p, bytes) else p.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()[:32]


def chave_de_arquivo(caminho: Path, *extras: str) -> str:
    return chave_de(caminho.read_bytes(), *extras)


class Gravador:
    def __init__(self, servico: str, raiz: Path | None = None) -> None:
        self.dir = (raiz or CAMINHOS.gravadas) / servico

    def caminho(self, chave: str) -> Path:
        return self.dir / f"{chave}.json"

    def ler(self, chave: str) -> dict[str, Any] | None:
        p = self.caminho(chave)
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    def gravar(self, chave: str, dados: dict[str, Any]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.caminho(chave).write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


def usar_servico_real(tem_chave: bool, modo: ModoNuvem, servico: str) -> bool:
    if modo == "real":
        if not tem_chave:
            raise RuntimeError(f"MONITOR_MODO_NUVEM=real, mas falta a chave de {servico} no .env")
        return True
    if modo == "simulado":
        return False
    return tem_chave


def executar(
    *,
    servico: str,
    chave: str,
    gravador: Gravador,
    usar_real: bool,
    modo: ModoNuvem,
    chamada_real: Callable[[], dict[str, Any]],
    simulado: Callable[[], dict[str, Any] | None],
) -> tuple[dict[str, Any] | None, Origem]:
    """Chama o serviço real, grava e devolve; senão gravação; senão heurística."""
    if usar_real:
        try:
            dados = chamada_real()
            gravador.gravar(chave, dados)
            return dados, "real"
        except Exception as erro:  # noqa: BLE001 — qualquer falha de rede/SDK cai no plano B
            if modo == "real":
                raise
            log.warning("%s falhou (%s); usando gravação ou simulação", servico, erro)
    gravado = gravador.ler(chave)
    if gravado is not None:
        return gravado, "gravado"
    return simulado(), "simulado"
