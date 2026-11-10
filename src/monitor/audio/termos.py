"""Termos críticos e sentimento negativo na transcrição da consulta (RF-33).

Detector puro: recebe a transcrição (``Transcricao``) e a análise do texto
(``AnaliseTexto``) já prontas e devolve Eventos. Não chama serviço nem lê arquivo.

Termo crítico = termo da lista curada do ``config`` que aparece

1. como entidade de saúde **não negada** do Azure (categoria ``SymptomOrSign``
   ou ``Diagnosis``) — ``fonte_termo = "entidade"``; ou
2. no texto, sem ter sido marcado pelo Azure (coloquialismo que o modelo não
   reconhece), e sem negação nas três palavras anteriores — ``fonte_termo = "lista"``.

O instante do evento é o da primeira palavra do termo na transcrição.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta

from monitor.audio.config import CONFIG, ConfigAudio
from monitor.eventos import Evento, Fonte, Severidade
from monitor.nuvem.azure_fala import Transcricao
from monitor.nuvem.azure_linguagem import AnaliseTexto
from monitor.nuvem.lexico import negado, normalizar

DETECTOR_TERMOS = "audio_termos/v1"
DETECTOR_SENTIMENTO = "audio_sentimento/v1"


@dataclass(frozen=True)
class Ocorrencia:
    termo: str  # forma curada, sem acento
    trecho: str  # como está escrito na transcrição
    offset: int  # posição no texto da transcrição
    fonte_termo: str  # "entidade" | "lista"
    categoria: str  # categoria do Azure, ou "lista"
    confianca: float | None


def _limpar(palavra: str) -> str:
    return re.sub(r"[^\w]", "", normalizar(palavra))


def _termo_da_lista(texto_entidade: str, cfg: ConfigAudio) -> str | None:
    """Termo curado mais longo contido no texto da entidade."""
    norm = normalizar(texto_entidade)
    achados = [t for t in cfg.termos_criticos if re.search(rf"\b{re.escape(t)}\b", norm)]
    return max(achados, key=len) if achados else None


def _sobrepoe(inicio: int, fim: int, outro_inicio: int, outro_fim: int) -> bool:
    return inicio < outro_fim and fim > outro_inicio


def achar_termos(analise: AnaliseTexto, texto: str, cfg: ConfigAudio = CONFIG) -> list[Ocorrencia]:
    """Todas as ocorrências de termo crítico não negado, na ordem do texto."""
    texto = unicodedata.normalize("NFC", texto)
    norm = normalizar(texto)  # mesmo comprimento do texto NFC: os offsets valem para os dois
    ocorrencias: list[Ocorrencia] = []
    negadas: list[tuple[int, int]] = []

    for e in analise.entidades:
        if e.categoria not in cfg.categorias_termo:
            continue
        if e.negada:
            negadas.append((e.offset, e.offset + e.comprimento))
            continue
        termo = _termo_da_lista(e.texto, cfg)
        if termo:
            ocorrencias.append(Ocorrencia(termo, e.texto, e.offset, "entidade", e.categoria, e.confianca))

    for termo in cfg.termos_criticos:
        for m in re.finditer(rf"\b{re.escape(termo)}\b", norm):
            ja_achado = any(o.termo == termo and _sobrepoe(m.start(), m.end(), o.offset, o.offset + len(o.trecho))
                            for o in ocorrencias)
            negado_pelo_azure = any(_sobrepoe(m.start(), m.end(), i, f) for i, f in negadas)
            if ja_achado or negado_pelo_azure or negado(norm, m.start()):
                continue
            ocorrencias.append(Ocorrencia(termo, texto[m.start():m.end()], m.start(), "lista", "lista", None))

    return sorted(ocorrencias, key=lambda o: o.offset)


def inicio_do_offset(transcricao: Transcricao, offset: int) -> float:
    """Segundo em que começa a palavra que contém ``offset`` no texto.

    Quando as palavras da transcrição correspondem uma a uma aos tokens do
    texto, usa o horário da palavra; senão, interpola pela posição no texto.
    """
    tokens = transcricao.texto.split()
    indice = len(transcricao.texto[:offset].split())
    if len(transcricao.palavras) == len(tokens) and indice < len(tokens):
        return transcricao.palavras[indice].inicio_s
    return round(offset / max(len(transcricao.texto), 1) * transcricao.duracao_s, 3)


def inicio_do_termo(transcricao: Transcricao, ocorrencia: Ocorrencia) -> float:
    """Casa a sequência de palavras do termo com as palavras da transcrição.

    A k-ésima ocorrência do termo no texto corresponde à k-ésima sequência
    de palavras igual ao termo (comparação sem acento e sem pontuação).
    """
    alvo = ocorrencia.termo.split()
    palavras = [_limpar(p.texto) for p in transcricao.palavras]
    inicios = [i for i in range(len(palavras) - len(alvo) + 1) if palavras[i:i + len(alvo)] == alvo]
    norm = normalizar(unicodedata.normalize("NFC", transcricao.texto))
    k = len(re.findall(rf"\b{re.escape(ocorrencia.termo)}\b", norm[:ocorrencia.offset]))
    if k < len(inicios):
        return transcricao.palavras[inicios[k]].inicio_s
    if inicios:
        return transcricao.palavras[inicios[0]].inicio_s
    return inicio_do_offset(transcricao, ocorrencia.offset)


def _mmss(segundos: float) -> str:
    return f"{int(segundos) // 60:02d}:{int(segundos) % 60:02d}"


def detectar(
    analise: AnaliseTexto,
    transcricao: Transcricao,
    paciente_id: str,
    inicio: datetime,
    cfg: ConfigAudio = CONFIG,
) -> list[Evento]:
    """Um evento ``termo_critico`` por termo (na primeira ocorrência) e um
    ``sentimento_negativo`` por frase negativa com confiança ≥ limiar."""
    origens = {"origem_transcricao": transcricao.origem, "origem_analise": analise.origem}
    eventos: list[Evento] = []

    ocorrencias = achar_termos(analise, transcricao.texto, cfg)
    for termo in dict.fromkeys(o.termo for o in ocorrencias):  # ordem da primeira aparição
        mesmas = [o for o in ocorrencias if o.termo == termo]
        primeira = mesmas[0]
        segundo = inicio_do_termo(transcricao, primeira)
        severidade = cfg.termos_criticos[termo]
        eventos.append(Evento(
            paciente_id=paciente_id,
            instante=inicio + timedelta(seconds=segundo),
            fonte=Fonte.AUDIO,
            tipo="termo_critico",
            severidade=severidade,
            descricao=f'Paciente relatou "{primeira.trecho}" aos {_mmss(segundo)} da consulta '
                      f"(termo crítico, severidade {severidade.name}).",
            detector=DETECTOR_TERMOS,
            valor=primeira.confianca,
            evidencia={
                "termo": termo,
                "trecho": primeira.trecho,
                "fonte_termo": primeira.fonte_termo,
                "categoria": primeira.categoria,
                "inicio_s": f"{segundo:.2f}",
                "ocorrencias": str(len(mesmas)),
                **origens,
            },
        ))

    for frase in analise.frases:
        if frase.sentimento != "negative" or frase.negativo < cfg.limiar_sentimento_negativo:
            continue
        segundo = inicio_do_offset(transcricao, frase.offset)
        eventos.append(Evento(
            paciente_id=paciente_id,
            instante=inicio + timedelta(seconds=segundo),
            fonte=Fonte.AUDIO,
            tipo="sentimento_negativo",
            severidade=Severidade.INFO,
            descricao=f'Frase com sentimento negativo aos {_mmss(segundo)} da consulta: "{frase.texto}".',
            detector=DETECTOR_SENTIMENTO,
            valor=frase.negativo,
            evidencia={"trecho": frase.texto, "negativo": f"{frase.negativo:.2f}", "inicio_s": f"{segundo:.2f}",
                       **origens},
        ))

    return sorted(eventos, key=lambda e: e.instante)
