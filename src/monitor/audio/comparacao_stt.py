"""Comparação de serviços de transcrição pela taxa de erro de palavras (WER, RF-35).

WER = (substituições + remoções + inserções) / palavras da referência,
contadas pela distância de edição em palavras, depois de passar referência e
hipótese para minúsculas, sem acento e sem pontuação.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from monitor.nuvem.azure_fala import ClienteFala, Transcricao
from monitor.nuvem.lexico import normalizar
from monitor.nuvem.openai_llm import ClienteLLM


def palavras_normalizadas(texto: str) -> list[str]:
    return re.sub(r"[^\w\s]", " ", normalizar(texto)).split()


def distancia_edicao(a: list[str], b: list[str]) -> int:
    """Levenshtein em palavras, com uma linha da tabela por vez."""
    anterior = list(range(len(b) + 1))
    for i, pa in enumerate(a, start=1):
        atual = [i]
        for j, pb in enumerate(b, start=1):
            atual.append(min(
                anterior[j] + 1,  # remoção
                atual[j - 1] + 1,  # inserção
                anterior[j - 1] + (pa != pb),  # substituição (ou acerto)
            ))
        anterior = atual
    return anterior[-1]


def wer(referencia: str, hipotese: str) -> float:
    ref = palavras_normalizadas(referencia)
    if not ref:
        raise ValueError("a referência do WER não tem palavras")
    return distancia_edicao(ref, palavras_normalizadas(hipotese)) / len(ref)


def _avaliar(transcricao: Transcricao | None, roteiro: str, sem_transcricao: str) -> dict[str, Any]:
    if transcricao is None:
        return {"wer": None, "origem": None, "motivo": sem_transcricao}
    if transcricao.origem == "simulado":
        return {"wer": None, "origem": "simulado",
                "motivo": "transcrição simulada é o próprio roteiro; o WER seria zero por construção"}
    return {"wer": wer(roteiro, transcricao.texto), "origem": transcricao.origem, "motivo": None,
            "texto": transcricao.texto}


def comparar_servicos(
    wav: Path,
    roteiro: str,
    cliente_fala: ClienteFala | None = None,
    cliente_llm: ClienteLLM | None = None,
    incluir_whisper: bool = True,
) -> dict[str, dict[str, Any]]:
    """WER do Azure Speech e do Whisper contra o roteiro lido na gravação.

    Só há número quando a transcrição é real ou gravada; senão ``wer`` é
    ``None`` e ``motivo`` diz por quê. ``incluir_whisper=False`` não chama a
    OpenAI (o Whisper é pago por minuto).
    """
    azure = (cliente_fala or ClienteFala()).transcrever(Path(wav))
    whisper = (cliente_llm or ClienteLLM()).transcrever_whisper(Path(wav)) if incluir_whisper else None
    return wer_por_servico(roteiro, azure, whisper, incluir_whisper)


def wer_por_servico(
    roteiro: str, azure: Transcricao, whisper: Transcricao | None, whisper_pedido: bool = True
) -> dict[str, dict[str, Any]]:
    """O mesmo que ``comparar_servicos``, com as transcrições já feitas (não paga o serviço duas vezes)."""
    sem_whisper = ("sem chave da OpenAI e sem gravação do Whisper para este áudio" if whisper_pedido
                   else "Whisper não pedido (use --whisper)")
    return {
        "azure": _avaliar(azure, roteiro, "sem transcrição do Azure"),
        "whisper": _avaliar(whisper, roteiro, sem_whisper),
    }
