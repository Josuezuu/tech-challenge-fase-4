"""Avaliação dos detectores sobre séries com anomalias plantadas (RF-65).

Para cada gravação:
1. planta ``n_anomalias`` com rótulo e roda o fluxo → recall, precisão, atraso;
2. roda a série original, **sem** plantio → alertas falsos por hora.

Casamento: um evento da mesma variável do rótulo dentro de
``[inicio, fim + tolerancia]`` é acerto. O rótulo conta como detectado se
tiver pelo menos um acerto; o atraso é do primeiro acerto até o início.
Evento fora de qualquer rótulo é falso positivo — inclusive o que vem de uma
condição real do paciente (ex.: BIDMC 21 com FC > 120 a gravação inteira),
porque o BIDMC não tem rótulo clínico.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from monitor.config import SEMENTE
from monitor.eventos import Evento
from monitor.sinais.config import AVALIACAO, CONFIG, INJECAO, ConfigAvaliacao, ConfigInjecao, ConfigSinais
from monitor.sinais.detectores import MonitorVitais
from monitor.sinais.fluxo import reproduzir
from monitor.sinais.injecao import TIPOS, Rotulo, plantar_aleatorio

INICIO_AVALIACAO = datetime(2026, 1, 1, 0, 0, 0)


def variavel_do_evento(evento: Evento) -> str:
    return evento.tipo.split("_")[0]  # spo2_baixa → spo2, fc_desvio → fc


def t_do_evento(evento: Evento, inicio: datetime = INICIO_AVALIACAO) -> float:
    return (evento.instante - inicio).total_seconds()


def rodar(df: pd.DataFrame, paciente_id: str, gravacao: str = "", config: ConfigSinais = CONFIG) -> tuple[list[Evento], MonitorVitais]:
    """Passa a série inteira pelo monitor, sem dormir; devolve os eventos e o monitor (latências)."""
    monitor = MonitorVitais(config, gravacao=gravacao)
    eventos: list[Evento] = []
    for amostra in reproduzir(df, paciente_id, INICIO_AVALIACAO):
        eventos.extend(monitor.processar(amostra))
    return eventos, monitor


def fora_da_faixa_na_mediana(df: pd.DataFrame, config: ConfigSinais = CONFIG) -> list[str]:
    """Variáveis cuja mediana da gravação inteira já está fora da faixa ALTA (condição real do paciente)."""
    fora: list[str] = []
    for lim in config.limiares:
        if lim.variavel not in df.columns:
            continue
        mediana = float(df[lim.variavel].median())
        if (lim.alta_abaixo is not None and mediana < lim.alta_abaixo) or (
            lim.alta_acima is not None and mediana > lim.alta_acima
        ):
            fora.append(lim.variavel)
    return fora


def casar(eventos: list[Evento], rotulos: list[Rotulo], tolerancia_s: float) -> tuple[list[float | None], int]:
    """Devolve o atraso de cada rótulo (``None`` = perdido) e quantos eventos caíram em algum rótulo."""
    atrasos: list[float | None] = []
    for r in rotulos:
        acertos = [t_do_evento(e) for e in eventos
                   if variavel_do_evento(e) == r.variavel and r.inicio_s <= t_do_evento(e) <= r.fim_s + tolerancia_s]
        atrasos.append(min(acertos) - r.inicio_s if acertos else None)
    verdadeiros = sum(
        1 for e in eventos
        if any(variavel_do_evento(e) == r.variavel and r.inicio_s <= t_do_evento(e) <= r.fim_s + tolerancia_s
               for r in rotulos)
    )
    return atrasos, verdadeiros


def _f1(precisao: float, recall: float) -> float:
    return 2 * precisao * recall / (precisao + recall) if precisao + recall else 0.0


def _media(valores: list[float]) -> float | None:
    return round(float(np.mean(valores)), 2) if valores else None


def avaliar(
    gravacoes: dict[str, pd.DataFrame],
    n_anomalias: int = AVALIACAO.anomalias_por_gravacao,
    semente: int = SEMENTE,
    config: ConfigSinais = CONFIG,
    injecao: ConfigInjecao = INJECAO,
    avaliacao: ConfigAvaliacao = AVALIACAO,
) -> dict[str, Any]:
    """``gravacoes``: nome → DataFrame (``t_s, fc, fr, spo2``...). Devolve os números prontos para o JSON."""
    tol = avaliacao.tolerancia_s
    por_tipo_atrasos: dict[str, list[float | None]] = defaultdict(list)
    eventos_plantio = verdadeiros = 0
    falsos_por_tipo: Counter[str] = Counter()
    eventos_limpos: Counter[str] = Counter()
    gravacoes_com_evento_limpo: list[str] = []
    horas = 0.0
    latencias: list[float] = []
    condicao_real: dict[str, list[str]] = {}
    eventos_condicao_real = 0

    for i, (nome, df) in enumerate(sorted(gravacoes.items())):
        plantado, rotulos = plantar_aleatorio(df, n_anomalias, semente + i, injecao)
        eventos, monitor = rodar(plantado, f"aval-{nome}", nome, config)
        latencias.extend(monitor.latencias_ms)
        atrasos, vp = casar(eventos, rotulos, tol)
        for r, a in zip(rotulos, atrasos):
            por_tipo_atrasos[r.tipo].append(a)
        eventos_plantio += len(eventos)
        verdadeiros += vp
        for e in eventos:
            if not any(variavel_do_evento(e) == r.variavel and r.inicio_s <= t_do_evento(e) <= r.fim_s + tol
                       for r in rotulos):
                falsos_por_tipo[e.tipo] += 1

        limpos, _ = rodar(df, f"aval-{nome}", nome, config)
        eventos_limpos.update(e.tipo for e in limpos)
        if limpos:
            gravacoes_com_evento_limpo.append(nome)
        fora = fora_da_faixa_na_mediana(df, config)
        if fora:
            condicao_real[nome] = fora
            eventos_condicao_real += sum(1 for e in limpos if variavel_do_evento(e) in fora)
        horas += (float(df["t_s"].max()) - float(df["t_s"].min()) + 1) / 3600

    por_tipo: dict[str, Any] = {}
    todos: list[float | None] = []
    for tipo in TIPOS:
        atrasos = por_tipo_atrasos.get(tipo, [])
        todos.extend(atrasos)
        achados = [a for a in atrasos if a is not None]
        por_tipo[tipo] = {
            "rotulos": len(atrasos),
            "detectados": len(achados),
            "recall": round(len(achados) / len(atrasos), 3) if atrasos else None,
            "atraso_medio_s": _media(achados),
        }
    achados_todos = [a for a in todos if a is not None]
    recall = len(achados_todos) / len(todos) if todos else 0.0
    precisao = verdadeiros / eventos_plantio if eventos_plantio else 0.0
    total_limpos = sum(eventos_limpos.values())
    return {
        "gravacoes": len(gravacoes),
        "anomalias_por_gravacao": n_anomalias,
        "semente": semente,
        "tolerancia_s": tol,
        "geral": {
            "rotulos": len(todos),
            "detectados": len(achados_todos),
            "recall": round(recall, 3),
            "eventos": eventos_plantio,
            "eventos_verdadeiros": verdadeiros,
            "precisao": round(precisao, 3),
            "f1": round(_f1(precisao, recall), 3),
            "atraso_medio_s": _media(achados_todos),
            "atraso_mediano_s": round(float(np.median(achados_todos)), 2) if achados_todos else None,
        },
        "por_tipo": por_tipo,
        "falsos_positivos_com_plantio_por_tipo_de_evento": dict(sorted(falsos_por_tipo.items())),
        "sem_plantio": {
            "horas": round(horas, 3),
            "eventos": total_limpos,
            "alertas_falsos_por_hora": round(total_limpos / horas, 2) if horas else None,
            "por_tipo_de_evento": dict(sorted(eventos_limpos.items())),
            "gravacoes_com_evento": gravacoes_com_evento_limpo,
            # Gravações cuja mediana já está fora da faixa: o evento é condição real, não alarme falso.
            "gravacoes_com_mediana_fora_da_faixa": condicao_real,
            "eventos_de_condicao_real": eventos_condicao_real,
            "alertas_falsos_por_hora_sem_condicao_real": (
                round((total_limpos - eventos_condicao_real) / horas, 2) if horas else None
            ),
        },
        "latencia_media_ms": round(float(np.mean(latencias)), 4) if latencias else None,
    }
