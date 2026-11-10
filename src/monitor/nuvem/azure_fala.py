"""Azure AI Speech: fala para texto em pt-BR com horário por palavra (RO-2.3).

Modo simulado: lê o texto do arquivo irmão ``<audio>.txt`` (o roteiro lido
na gravação) e distribui as palavras uniformemente pela duração do áudio.
"""

from __future__ import annotations

import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import soundfile as sf

from monitor.config import Credenciais, ModoNuvem, carregar_credenciais, modo_nuvem
from monitor.nuvem.gravacao import Gravador, Origem, chave_de_arquivo, executar, usar_servico_real

TICKS_POR_SEGUNDO = 10_000_000  # o SDK mede Offset e Duration em unidades de 100 ns


@dataclass(frozen=True)
class Palavra:
    texto: str
    inicio_s: float
    fim_s: float
    confianca: float | None = None


@dataclass(frozen=True)
class Transcricao:
    texto: str
    palavras: tuple[Palavra, ...]
    idioma: str
    duracao_s: float
    servico: str  # "azure" | "whisper"
    origem: Origem

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["palavras"] = [asdict(p) for p in self.palavras]
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any], origem: Origem | None = None) -> Transcricao:
        return cls(
            texto=d["texto"],
            palavras=tuple(Palavra(**p) for p in d["palavras"]),
            idioma=d["idioma"],
            duracao_s=float(d["duracao_s"]),
            servico=d["servico"],
            origem=origem or d.get("origem", "gravado"),
        )


def duracao_audio(caminho: Path) -> float:
    return float(sf.info(str(caminho)).duration)


def transcricao_simulada(caminho: Path, idioma: str, servico: str = "azure") -> dict[str, Any]:
    roteiro = caminho.with_suffix(".txt")
    texto = roteiro.read_text(encoding="utf-8").strip() if roteiro.exists() else ""
    duracao = duracao_audio(caminho)
    tokens = texto.split()
    passo = duracao / max(len(tokens), 1)
    palavras = [
        {"texto": t.strip(".,;:!?\"'"), "inicio_s": round(i * passo, 3), "fim_s": round((i + 1) * passo, 3), "confianca": None}
        for i, t in enumerate(tokens)
    ]
    return {"texto": texto, "palavras": palavras, "idioma": idioma, "duracao_s": duracao, "servico": servico}


class ClienteFala:
    def __init__(
        self,
        credenciais: Credenciais | None = None,
        modo: ModoNuvem | None = None,
        gravador: Gravador | None = None,
    ) -> None:
        self.credenciais = credenciais or carregar_credenciais()
        self.modo = modo or modo_nuvem()
        self.gravador = gravador or Gravador("azure_fala")
        self.usar_real = usar_servico_real(self.credenciais.tem_azure_fala, self.modo, "Azure Speech")

    def transcrever(self, caminho_wav: Path, idioma: str = "pt-BR", timeout_s: float = 600) -> Transcricao:
        caminho_wav = Path(caminho_wav)
        dados, origem = executar(
            servico="Azure Speech",
            chave=chave_de_arquivo(caminho_wav, idioma),
            gravador=self.gravador,
            usar_real=self.usar_real,
            modo=self.modo,
            chamada_real=lambda: self._transcrever_azure(caminho_wav, idioma, timeout_s),
            simulado=lambda: transcricao_simulada(caminho_wav, idioma),
        )
        assert dados is not None
        return Transcricao.from_dict(dados, origem)

    def _transcrever_azure(self, caminho: Path, idioma: str, timeout_s: float) -> dict[str, Any]:
        import json

        import azure.cognitiveservices.speech as speechsdk

        cfg = speechsdk.SpeechConfig(
            subscription=self.credenciais.azure_speech_key, region=self.credenciais.azure_speech_region
        )
        cfg.speech_recognition_language = idioma
        cfg.request_word_level_timestamps()
        cfg.output_format = speechsdk.OutputFormat.Detailed
        audio = speechsdk.audio.AudioConfig(filename=str(caminho))
        reconhecedor = speechsdk.SpeechRecognizer(speech_config=cfg, audio_config=audio)

        fim = threading.Event()
        trechos: list[str] = []
        palavras: list[dict[str, Any]] = []
        erros: list[str] = []

        def reconhecido(evt: Any) -> None:
            if evt.result.reason != speechsdk.ResultReason.RecognizedSpeech:
                return
            trechos.append(evt.result.text)
            detalhe = json.loads(evt.result.json)
            melhores = detalhe.get("NBest") or []
            for w in melhores[0].get("Words", []) if melhores else []:
                inicio = w["Offset"] / TICKS_POR_SEGUNDO
                palavras.append({
                    "texto": w["Word"],
                    "inicio_s": round(inicio, 3),
                    "fim_s": round(inicio + w["Duration"] / TICKS_POR_SEGUNDO, 3),
                    "confianca": w.get("Confidence"),
                })

        def cancelado(evt: Any) -> None:
            if evt.cancellation_details.reason == speechsdk.CancellationReason.Error:
                erros.append(str(evt.cancellation_details.error_details))
            fim.set()

        reconhecedor.recognized.connect(reconhecido)
        reconhecedor.canceled.connect(cancelado)
        reconhecedor.session_stopped.connect(lambda _evt: fim.set())
        reconhecedor.start_continuous_recognition()
        terminou = fim.wait(timeout=timeout_s)
        reconhecedor.stop_continuous_recognition()
        if erros:
            raise RuntimeError(f"Azure Speech: {erros[0]}")
        if not terminou:
            raise TimeoutError(f"Azure Speech não terminou em {timeout_s}s")
        return {
            "texto": " ".join(t for t in trechos if t).strip(),
            "palavras": palavras,
            "idioma": idioma,
            "duracao_s": duracao_audio(caminho),
            "servico": "azure",
        }
