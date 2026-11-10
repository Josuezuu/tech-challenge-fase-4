"""Relatório automático da sessão em Markdown (RF-06).

Tabela de eventos montada aqui; o parágrafo de resumo é redigido pela LLM a
partir dos mesmos dados estruturados (nunca vê o vídeo). Sem chave, sai o
texto do ``texto_modelo_fixo``, e o relatório diz qual foi a origem.
"""

from __future__ import annotations

import os
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from monitor.config import RAIZ
from monitor.eventos import Evento
from monitor.nuvem.openai_llm import ClienteLLM, Redacao
from monitor.video.fisioterapia import ResultadoFisioterapia

INSTRUCOES = (
    "Você redige, para a equipe de enfermagem, o resumo de uma sessão de monitoramento por vídeo. "
    "Escreva um único parágrafo em português do Brasil, objetivo, com no máximo 5 frases. "
    "Use apenas os dados do JSON; não invente horários, números nem diagnósticos. "
    "Comece pelo evento mais grave; se não houver evento, diga que a sessão transcorreu sem ocorrências."
)

NOMES = {
    "queda": "queda",
    "saida_do_leito": "saída do leito",
    "imobilidade_prolongada": "imobilidade prolongada",
    "paciente_ausente": "paciente ausente",
    "movimentacao_atipica": "movimentação atípica",
    "amplitude_insuficiente": "amplitude insuficiente",
}


def dados_da_sessao(
    nome: str,
    cenario: str,
    paciente_id: str,
    inicio: datetime,
    duracao_s: float,
    eventos: list[Evento],
    fisio: ResultadoFisioterapia | None = None,
) -> dict[str, Any]:
    dados: dict[str, Any] = {
        "sessao": nome,
        "cenario": cenario,
        "paciente_id": paciente_id,
        "inicio": inicio.isoformat(timespec="seconds"),
        "fim": (inicio + timedelta(seconds=duracao_s)).isoformat(timespec="seconds"),
        "duracao_min": round(duracao_s / 60, 1),
        "eventos": [
            {"horario": e.instante.strftime("%H:%M:%S"), "tipo": e.tipo, "severidade": e.severidade.name,
             "valor": e.valor, "descricao": e.descricao}
            for e in sorted(eventos, key=lambda e: (-e.severidade, e.instante))
        ],
    }
    if fisio is not None:
        dados["fisioterapia"] = {
            "exercicio": fisio.exercicio,
            "repeticoes": fisio.total,
            "incompletas": fisio.incompletas,
            "amplitude_media_graus": None if fisio.amplitude_media is None else round(fisio.amplitude_media, 1),
        }
    return dados


def texto_modelo_fixo(dados: dict[str, Any]) -> str:
    """Parágrafo determinístico, usado sem chave da OpenAI."""
    frases = [f"Sessão de {dados['duracao_min']} min ({dados['cenario']}) do paciente {dados['paciente_id']}, "
              f"de {dados['inicio'][11:]} a {dados['fim'][11:]}."]
    fisio = dados.get("fisioterapia")
    if fisio:
        media = fisio["amplitude_media_graus"]
        frases.append(f"Exercício {fisio['exercicio'].replace('_', ' ')}: {fisio['repeticoes']} repetições, "
                      f"{fisio['incompletas']} com amplitude insuficiente"
                      + (f", amplitude média de {media:.0f}°." if media is not None else "."))
    eventos = dados["eventos"]
    if not eventos:
        frases.append("Nenhum evento registrado no período.")
    else:
        mais_grave = eventos[0]
        frases.append(f"Evento mais grave: {NOMES.get(mais_grave['tipo'], mais_grave['tipo'])} às "
                      f"{mais_grave['horario']} ({mais_grave['descricao']})")
        contagem = Counter(e["tipo"] for e in eventos)
        lista = ", ".join(f"{n} × {NOMES.get(t, t)}" for t, n in contagem.items())
        frases.append(f"Total de {len(eventos)} evento(s): {lista}.")
    return " ".join(frases)


def _link(evidencia: str, pasta_relatorio: Path) -> str:
    alvo = Path(evidencia)
    alvo = alvo if alvo.is_absolute() else RAIZ / alvo
    return Path(os.path.relpath(alvo, pasta_relatorio)).as_posix()


def escrever_relatorio(
    destino: Path,
    dados: dict[str, Any],
    eventos: list[Evento],
    cliente: ClienteLLM,
    video_anotado: str | None = None,
    s_por_quadro: float | None = None,
) -> Redacao:
    redacao = cliente.redigir(INSTRUCOES, dados, texto_modelo_fixo)
    pasta = destino.parent
    linhas = [
        f"# Sessão {dados['sessao']} — {dados['cenario']}",
        "",
        f"Paciente **{dados['paciente_id']}** · {dados['inicio'].replace('T', ' ')} a {dados['fim'][11:]} "
        f"· {dados['duracao_min']} min",
    ]
    if video_anotado:
        linhas.append(f"Vídeo anotado: [{Path(video_anotado).name}]({_link(video_anotado, pasta)})")
    if s_por_quadro is not None:
        linhas.append(f"Inferência em CPU: {s_por_quadro:.2f} s por quadro analisado")
    linhas += ["", "## Resumo", "", redacao.texto, "", f"_Texto: {redacao.origem}_", ""]
    fisio = dados.get("fisioterapia")
    if fisio:
        media = fisio["amplitude_media_graus"]
        linhas += ["## Fisioterapia", "", "| Exercício | Repetições | Incompletas | Amplitude média |",
                   "|---|---|---|---|",
                   f"| {fisio['exercicio']} | {fisio['repeticoes']} | {fisio['incompletas']} | "
                   f"{'-' if media is None else f'{media:.0f}°'} |", ""]
    linhas += ["## Eventos", ""]
    if not eventos:
        linhas.append("Nenhum evento.")
    else:
        linhas += ["| Horário | Tipo | Severidade | Valor | Descrição | Evidência |", "|---|---|---|---|---|---|"]
        for e in sorted(eventos, key=lambda e: e.instante):
            recorte = e.evidencia.get("recorte")
            link = f"[quadro]({_link(recorte, pasta)})" if recorte else "-"
            valor = "-" if e.valor is None else f"{e.valor:g}"
            linhas.append(f"| {e.instante:%H:%M:%S} | {e.tipo} | {e.severidade.name} | {valor} | "
                          f"{e.descricao} | {link} |")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return redacao
