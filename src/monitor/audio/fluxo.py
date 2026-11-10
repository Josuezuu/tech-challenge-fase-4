"""Fluxo completo de um áudio de consulta: converte, transcreve, analisa,
acha termos críticos e, com uma referência do paciente, mede alteração vocal.

É a única parte que junta E/S (arquivo, serviços de nuvem) com os
detectores puros; ``experiments/run_audio.py`` e ``avaliacao`` a usam.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from monitor.audio import acustica, comparacao, termos
from monitor.audio.acustica import AtributosVoz
from monitor.audio.analise import analisar
from monitor.audio.comparacao import ResultadoVoz
from monitor.audio.comparacao_stt import wer_por_servico
from monitor.audio.conversao import DIR_SAIDA, para_wav
from monitor.audio.transcricao import transcrever, transcrever_whisper
from monitor.config import RAIZ
from monitor.eventos import Evento
from monitor.nuvem.azure_fala import ClienteFala, Transcricao
from monitor.nuvem.azure_linguagem import AnaliseTexto, ClienteLinguagem
from monitor.nuvem.openai_llm import ClienteLLM


def relativo(caminho: Path) -> str:
    """Caminho relativo à raiz do repositório (convenção das evidências)."""
    try:
        return Path(caminho).resolve().relative_to(RAIZ).as_posix()
    except ValueError:
        return Path(caminho).as_posix()


@dataclass(frozen=True)
class Clientes:
    fala: ClienteFala
    linguagem: ClienteLinguagem
    llm: ClienteLLM

    @classmethod
    def padrao(cls) -> Clientes:
        return cls(ClienteFala(), ClienteLinguagem(), ClienteLLM())


@dataclass(frozen=True)
class ResultadoAudio:
    audio: Path
    wav: Path
    paciente_id: str
    inicio: datetime
    transcricao: Transcricao
    analise: AnaliseTexto
    atributos: AtributosVoz
    referencia: Path | None
    atributos_referencia: AtributosVoz | None
    voz: ResultadoVoz | None
    stt: dict[str, dict[str, Any]] | None
    eventos: tuple[Evento, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "audio": relativo(self.audio),
            "wav": relativo(self.wav),
            "paciente_id": self.paciente_id,
            "inicio": self.inicio.isoformat(),
            "origens": {"transcricao": self.transcricao.origem, "analise": self.analise.origem},
            "transcricao": self.transcricao.to_dict(),
            "analise": self.analise.to_dict(),
            "atributos": self.atributos.to_dict(),
            "referencia": relativo(self.referencia) if self.referencia else None,
            "atributos_referencia": self.atributos_referencia.to_dict() if self.atributos_referencia else None,
            "comparacao_voz": self.voz.to_dict() if self.voz else None,
            "stt": self.stt,
            "eventos": [e.to_dict() for e in self.eventos],
        }


def _wav(audio: Path, dir_saida: Path) -> Path:
    destino = dir_saida / f"{audio.stem}.wav"
    return audio if audio.resolve() == destino.resolve() else para_wav(audio, destino)


def _roteiro(audio: Path) -> str | None:
    caminho = audio.with_suffix(".txt")
    return caminho.read_text(encoding="utf-8").strip() if caminho.exists() else None


def processar(
    audio: Path,
    paciente_id: str,
    inicio: datetime,
    referencia: Path | None = None,
    whisper: bool = False,
    clientes: Clientes | None = None,
    dir_saida: Path = DIR_SAIDA,
) -> ResultadoAudio:
    audio = Path(audio)
    clientes = clientes or Clientes.padrao()
    wav = _wav(audio, dir_saida)
    transcricao = transcrever(wav, clientes.fala)
    analise = analisar(transcricao, clientes.linguagem)
    eventos = termos.detectar(analise, transcricao, paciente_id, inicio)
    atributos = acustica.extrair(wav, transcricao)

    atributos_ref: AtributosVoz | None = None
    voz: ResultadoVoz | None = None
    if referencia is not None:
        wav_ref = _wav(Path(referencia), dir_saida)
        atributos_ref = acustica.extrair(wav_ref, transcrever(wav_ref, clientes.fala))
        voz = comparacao.comparar(atributos_ref, atributos)
        eventos += comparacao.detectar(voz, paciente_id, inicio)

    roteiro = _roteiro(audio)
    stt = None
    if roteiro:
        transcricao_whisper = transcrever_whisper(wav, clientes.llm) if whisper else None
        stt = wer_por_servico(roteiro, transcricao, transcricao_whisper, whisper_pedido=whisper)

    evidencia_audio = {"audio": relativo(audio)}
    if referencia is not None:
        evidencia_audio["referencia"] = relativo(Path(referencia))
    eventos = [dataclasses.replace(e, evidencia={**e.evidencia, **evidencia_audio}) for e in eventos]

    return ResultadoAudio(
        audio=audio, wav=wav, paciente_id=paciente_id, inicio=inicio, transcricao=transcricao,
        analise=analise, atributos=atributos, referencia=Path(referencia) if referencia else None,
        atributos_referencia=atributos_ref, voz=voz, stt=stt,
        eventos=tuple(sorted(eventos, key=lambda e: e.instante)),
    )
