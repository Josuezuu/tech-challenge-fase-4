"""OpenAI: redação de texto (alerta, relatório de sessão) e Whisper como linha de base.

A LLM só redige a partir de dados estruturados que recebe; nunca vê mídia
bruta. Sem chave, ``redigir`` usa o modelo fixo passado pelo chamador e
``transcrever_whisper`` devolve a gravação, se houver, ou ``None``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from monitor.config import Credenciais, ModoNuvem, carregar_credenciais, modo_nuvem
from monitor.nuvem.azure_fala import Transcricao, duracao_audio
from monitor.nuvem.gravacao import Gravador, Origem, chave_de, chave_de_arquivo, executar, usar_servico_real


@dataclass(frozen=True)
class Redacao:
    texto: str
    origem: Origem


class ClienteLLM:
    def __init__(
        self,
        credenciais: Credenciais | None = None,
        modo: ModoNuvem | None = None,
        raiz_gravacoes: Path | None = None,
    ) -> None:
        self.credenciais = credenciais or carregar_credenciais()
        self.modo = modo or modo_nuvem()
        self.gravador_texto = Gravador("openai_texto", raiz_gravacoes)
        self.gravador_whisper = Gravador("openai_whisper", raiz_gravacoes)
        self.usar_real = usar_servico_real(self.credenciais.tem_openai, self.modo, "OpenAI")
        self._cliente: Any = None

    def _sdk(self) -> Any:
        if self._cliente is None:
            from openai import OpenAI

            self._cliente = OpenAI(api_key=self.credenciais.openai_api_key)
        return self._cliente

    def redigir(
        self,
        instrucoes: str,
        dados: dict[str, Any],
        modelo_fixo: Callable[[dict[str, Any]], str],
        max_tokens: int = 400,
    ) -> Redacao:
        conteudo = json.dumps(dados, ensure_ascii=False, sort_keys=True, default=str)
        modelo = self.credenciais.openai_modelo

        def real() -> dict[str, Any]:
            resp = self._sdk().chat.completions.create(
                model=modelo,
                messages=[
                    {"role": "system", "content": instrucoes},
                    {"role": "user", "content": conteudo},
                ],
                temperature=0.2,
                max_completion_tokens=max_tokens,
            )
            return {"texto": (resp.choices[0].message.content or "").strip(), "modelo": modelo}

        resposta, origem = executar(
            servico="OpenAI",
            chave=chave_de(modelo, instrucoes, conteudo),
            gravador=self.gravador_texto,
            usar_real=self.usar_real,
            modo=self.modo,
            chamada_real=real,
            simulado=lambda: {"texto": modelo_fixo(dados)},
        )
        assert resposta is not None
        return Redacao(texto=resposta["texto"], origem=origem)

    def transcrever_whisper(self, caminho_audio: Path, idioma: str = "pt") -> Transcricao | None:
        caminho_audio = Path(caminho_audio)

        def real() -> dict[str, Any]:
            with caminho_audio.open("rb") as f:
                resp = self._sdk().audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    language=idioma,
                    response_format="verbose_json",
                    timestamp_granularities=["word"],
                )
            palavras = [
                {"texto": w.word, "inicio_s": float(w.start), "fim_s": float(w.end), "confianca": None}
                for w in (getattr(resp, "words", None) or [])
            ]
            return {"texto": resp.text.strip(), "palavras": palavras, "idioma": idioma,
                    "duracao_s": duracao_audio(caminho_audio), "servico": "whisper"}

        dados, origem = executar(
            servico="Whisper",
            chave=chave_de_arquivo(caminho_audio, "whisper-1", idioma),
            gravador=self.gravador_whisper,
            usar_real=self.usar_real,
            modo=self.modo,
            chamada_real=real,
            simulado=lambda: None,
        )
        return None if dados is None else Transcricao.from_dict(dados, origem)
