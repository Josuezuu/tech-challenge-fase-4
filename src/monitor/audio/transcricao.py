"""Transcrição da consulta (RF-31): Azure Speech pt-BR; Whisper como linha de base.

Os clientes de ``monitor.nuvem`` decidem entre real, gravado e simulado;
sem chave, o Azure devolve o roteiro ``<audio>.txt`` com ``origem="simulado"``.
"""

from __future__ import annotations

from pathlib import Path

from monitor.nuvem.azure_fala import ClienteFala, Transcricao
from monitor.nuvem.openai_llm import ClienteLLM


def transcrever(wav: Path, cliente: ClienteFala | None = None) -> Transcricao:
    return (cliente or ClienteFala()).transcrever(Path(wav))


def transcrever_whisper(wav: Path, cliente: ClienteLLM | None = None) -> Transcricao | None:
    """``None`` quando não há chave da OpenAI nem gravação para este áudio."""
    return (cliente or ClienteLLM()).transcrever_whisper(Path(wav))
