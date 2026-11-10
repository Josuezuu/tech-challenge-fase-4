"""Leitura dos eventos de todas as fontes e gravação dos alertas (RF-64)."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from monitor.alertas.motor import MotorAlertas
from monitor.eventos import Alerta, Evento, carregar_eventos, salvar_jsonl


def gravar_alertas(alertas: Iterable[Alerta], caminho: Path) -> int:
    return salvar_jsonl(caminho, alertas)


def ler_eventos(arquivos: Iterable[Path]) -> list[Evento]:
    eventos: list[Evento] = []
    for caminho in arquivos:
        eventos.extend(carregar_eventos(Path(caminho)))
    return eventos


def processar_arquivos(arquivos: Iterable[Path], motor: MotorAlertas | None = None) -> list[Alerta]:
    """Lê vários ``eventos/*.jsonl`` e passa tudo, em ordem de instante, pelo motor."""
    return (motor or MotorAlertas()).processar_todos(ler_eventos(arquivos))
