"""Azure AI Language: sentimento, frases-chave e Text Analytics for health (RO-2.4).

O antigo "Text Analytics" dos Cognitive Services hoje vive dentro do Azure AI
Language; o SDK continua sendo ``azure-ai-textanalytics``. O Text Analytics
for health aceita português na API hospedada (``language="pt"``).

Modo simulado: ``monitor.nuvem.lexico``.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from monitor.config import Credenciais, ModoNuvem, carregar_credenciais, modo_nuvem
from monitor.nuvem import lexico
from monitor.nuvem.gravacao import Gravador, Origem, chave_de, executar, usar_servico_real


@dataclass(frozen=True)
class FraseSentimento:
    texto: str
    sentimento: str  # positive | neutral | negative | mixed
    positivo: float
    neutro: float
    negativo: float
    offset: int


@dataclass(frozen=True)
class EntidadeSaude:
    texto: str
    categoria: str  # SymptomOrSign, MedicationName, Dosage, Frequency, MedicationRoute, Diagnosis...
    offset: int
    comprimento: int
    confianca: float
    normalizado: str | None
    negada: bool


@dataclass(frozen=True)
class AnaliseTexto:
    sentimento: str
    frases: tuple[FraseSentimento, ...]
    frases_chave: tuple[str, ...]
    entidades: tuple[EntidadeSaude, ...]
    origem: Origem

    def to_dict(self) -> dict[str, Any]:
        return {
            "sentimento": self.sentimento,
            "frases": [asdict(f) for f in self.frases],
            "frases_chave": list(self.frases_chave),
            "entidades": [asdict(e) for e in self.entidades],
            "origem": self.origem,
        }


def _analise_de(d: dict[str, Any], origem: Origem) -> AnaliseTexto:
    return AnaliseTexto(
        sentimento=d["sentimento"],
        frases=tuple(FraseSentimento(**f) for f in d["frases"]),
        frases_chave=tuple(d["frases_chave"]),
        entidades=tuple(EntidadeSaude(**e) for e in d["entidades"]),
        origem=origem,
    )


RE_FRASE = re.compile(r"[^.!?]+[.!?]?")


def analise_simulada(texto: str) -> dict[str, Any]:
    frases = []
    for m in RE_FRASE.finditer(texto):
        trecho = m.group().strip()
        if not trecho:
            continue
        rotulo, p, neu, n = lexico.sentimento(trecho)
        frases.append({"texto": trecho, "sentimento": rotulo, "positivo": p, "neutro": neu, "negativo": n,
                       "offset": m.start() + (len(m.group()) - len(m.group().lstrip()))})
    rotulos = {f["sentimento"] for f in frases}
    geral = "neutral" if not frases else (
        "mixed" if {"positive", "negative"} <= rotulos else
        "negative" if "negative" in rotulos else "positive" if "positive" in rotulos else "neutral"
    )
    entidades = lexico.entidades(texto)
    chave = sorted({e["texto"].lower() for e in entidades if e["categoria"] in ("SymptomOrSign", "Diagnosis", "MedicationName")})
    return {"sentimento": geral, "frases": frases, "frases_chave": chave, "entidades": entidades}


class ClienteLinguagem:
    def __init__(
        self,
        credenciais: Credenciais | None = None,
        modo: ModoNuvem | None = None,
        gravador: Gravador | None = None,
    ) -> None:
        self.credenciais = credenciais or carregar_credenciais()
        self.modo = modo or modo_nuvem()
        self.gravador = gravador or Gravador("azure_linguagem")
        self.usar_real = usar_servico_real(self.credenciais.tem_azure_linguagem, self.modo, "Azure AI Language")
        self._cliente: Any = None

    def _sdk(self) -> Any:
        if self._cliente is None:
            from azure.ai.textanalytics import TextAnalyticsClient
            from azure.core.credentials import AzureKeyCredential

            self._cliente = TextAnalyticsClient(
                endpoint=self.credenciais.azure_language_endpoint,
                credential=AzureKeyCredential(self.credenciais.azure_language_key),
            )
        return self._cliente

    def analisar(self, texto: str, idioma: str = "pt-BR", idioma_saude: str = "pt") -> AnaliseTexto:
        """Sentimento por frase, frases-chave e entidades de saúde de um texto."""
        dados, origem = executar(
            servico="Azure AI Language",
            chave=chave_de("analisar", texto, idioma, idioma_saude),
            gravador=self.gravador,
            usar_real=self.usar_real,
            modo=self.modo,
            chamada_real=lambda: self._analisar_azure(texto, idioma, idioma_saude),
            simulado=lambda: analise_simulada(texto),
        )
        assert dados is not None
        return _analise_de(dados, origem)

    def entidades_saude(self, texto: str, idioma: str = "pt") -> tuple[tuple[EntidadeSaude, ...], Origem]:
        """Só o Text Analytics for health (usado nas prescrições)."""
        dados, origem = executar(
            servico="Text Analytics for health",
            chave=chave_de("saude", texto, idioma),
            gravador=self.gravador,
            usar_real=self.usar_real,
            modo=self.modo,
            chamada_real=lambda: {"entidades": self._saude_azure(texto, idioma)},
            simulado=lambda: {"entidades": lexico.entidades(texto)},
        )
        assert dados is not None
        return tuple(EntidadeSaude(**e) for e in dados["entidades"]), origem

    def _analisar_azure(self, texto: str, idioma: str, idioma_saude: str) -> dict[str, Any]:
        cliente = self._sdk()
        doc = cliente.analyze_sentiment([texto], language=idioma)[0]
        if doc.is_error:
            raise RuntimeError(f"sentimento: {doc.error}")
        frases = [
            {
                "texto": s.text,
                "sentimento": s.sentiment,
                "positivo": s.confidence_scores.positive,
                "neutro": s.confidence_scores.neutral,
                "negativo": s.confidence_scores.negative,
                "offset": s.offset,
            }
            for s in doc.sentences
        ]
        chave = cliente.extract_key_phrases([texto], language=idioma)[0]
        if chave.is_error:
            raise RuntimeError(f"frases-chave: {chave.error}")
        return {
            "sentimento": doc.sentiment,
            "frases": frases,
            "frases_chave": list(chave.key_phrases),
            "entidades": self._saude_azure(texto, idioma_saude),
        }

    def _saude_azure(self, texto: str, idioma: str) -> list[dict[str, Any]]:
        poller = self._sdk().begin_analyze_healthcare_entities([texto], language=idioma)
        docs = list(poller.result())
        doc = docs[0]
        if doc.is_error:
            raise RuntimeError(f"Text Analytics for health: {doc.error}")
        saida = []
        for e in doc.entities:
            certeza = getattr(e.assertion, "certainty", None) if e.assertion else None
            saida.append({
                "texto": e.text,
                "categoria": str(e.category),
                "offset": e.offset,
                "comprimento": e.length,
                "confianca": e.confidence_score,
                "normalizado": e.normalized_text,
                "negada": bool(certeza and str(certeza).startswith("negative")),
            })
        return saida
