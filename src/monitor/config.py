"""Configuração global: caminhos, credenciais e modo da nuvem.

Os parâmetros de cada detector ficam no ``config.py`` do próprio subpacote
(``monitor.sinais.config``, ``monitor.video.config``...), para que cada fonte
seja ajustada sem tocar nas outras.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parents[2]
SEMENTE = 42

ModoNuvem = Literal["auto", "real", "simulado"]


@dataclass(frozen=True)
class Caminhos:
    raiz: Path = RAIZ
    dados: Path = field(default=RAIZ / "data")
    brutos: Path = field(default=RAIZ / "data" / "raw")
    amostras: Path = field(default=RAIZ / "data" / "amostras")
    gravacoes: Path = field(default=RAIZ / "data" / "gravacoes")
    resultados: Path = field(default=RAIZ / "results")
    eventos: Path = field(default=RAIZ / "results" / "eventos")
    evidencias: Path = field(default=RAIZ / "results" / "evidencias")
    gravadas: Path = field(default=RAIZ / "docs" / "execucoes_gravadas")
    modelos: Path = field(default=RAIZ / "models")


CAMINHOS = Caminhos()


@dataclass(frozen=True)
class Credenciais:
    azure_speech_key: str | None
    azure_speech_region: str | None
    azure_language_key: str | None
    azure_language_endpoint: str | None
    openai_api_key: str | None
    openai_modelo: str

    @property
    def tem_azure_fala(self) -> bool:
        return bool(self.azure_speech_key and self.azure_speech_region)

    @property
    def tem_azure_linguagem(self) -> bool:
        return bool(self.azure_language_key and self.azure_language_endpoint)

    @property
    def tem_openai(self) -> bool:
        return bool(self.openai_api_key)


def _env(nome: str) -> str | None:
    valor = os.getenv(nome, "").strip()
    return valor or None


def carregar_credenciais() -> Credenciais:
    load_dotenv(RAIZ / ".env", override=False)
    return Credenciais(
        azure_speech_key=_env("AZURE_SPEECH_KEY"),
        azure_speech_region=_env("AZURE_SPEECH_REGION"),
        azure_language_key=_env("AZURE_LANGUAGE_KEY"),
        azure_language_endpoint=_env("AZURE_LANGUAGE_ENDPOINT"),
        openai_api_key=_env("OPENAI_API_KEY"),
        openai_modelo=_env("OPENAI_MODEL") or "gpt-4o-mini",
    )


def modo_nuvem() -> ModoNuvem:
    load_dotenv(RAIZ / ".env", override=False)
    modo = (_env("MONITOR_MODO_NUVEM") or "auto").lower()
    if modo not in ("auto", "real", "simulado"):
        raise ValueError(f"MONITOR_MODO_NUVEM inválido: {modo!r} (use auto, real ou simulado)")
    return modo  # type: ignore[return-value]
