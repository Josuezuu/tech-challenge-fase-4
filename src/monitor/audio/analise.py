"""Análise da transcrição com o Azure AI Language (RF-32): sentimento por
frase, frases-chave e entidades de saúde (Text Analytics for health)."""

from __future__ import annotations

from monitor.nuvem.azure_fala import Transcricao
from monitor.nuvem.azure_linguagem import AnaliseTexto, ClienteLinguagem


def analisar(transcricao: Transcricao, cliente: ClienteLinguagem | None = None) -> AnaliseTexto:
    if not transcricao.texto.strip():
        # O serviço recusa documento vazio; transcrição vazia não tem o que analisar.
        return AnaliseTexto("neutral", (), (), (), "simulado")
    return (cliente or ClienteLinguagem()).analisar(transcricao.texto)
