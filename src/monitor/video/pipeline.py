"""Sessão de vídeo de ponta a ponta: inferência → análise → anotação → Eventos → relatório.

Só orquestra: cada passo está no seu módulo. É o que ``experiments/run_video.py``
e o teste ``lento`` chamam.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Literal

from monitor.config import CAMINHOS, RAIZ
from monitor.eventos import Evento, salvar_jsonl
from monitor.movimentacao import detector as movimentacao
from monitor.movimentacao.config import ConfigMovimentacao
from monitor.nuvem.openai_llm import ClienteLLM
from monitor.video.anotacao import gravar_anotado
from monitor.video.config import ConfigFisioterapia, ConfigInferencia, ConfigPaciente, ConfigQuarto
from monitor.video.fisioterapia import ResultadoFisioterapia, analisar_fisioterapia
from monitor.video.inferencia import ResultadoInferencia, analisar_video
from monitor.video.paciente import escolher_paciente
from monitor.video.quarto import EstadoQuadro, calcular_estados, detectar_ausencia, detectar_quedas, estimar_zona
from monitor.video.relatorio import dados_da_sessao, escrever_relatorio

Cenario = Literal["quarto", "fisioterapia"]


@dataclass(frozen=True)
class ResultadoSessao:
    eventos_video: list[Evento]
    eventos_movimentacao: list[Evento]
    inferencia: ResultadoInferencia
    fisio: ResultadoFisioterapia | None
    video_anotado: Path | None
    relatorio: Path | None
    texto_origem: str | None

    @property
    def eventos(self) -> list[Evento]:
        return sorted(self.eventos_video + self.eventos_movimentacao, key=lambda e: e.instante)


def relativo(caminho: Path) -> str:
    """Caminho de evidência relativo à raiz do repo (absoluto se estiver fora dela)."""
    try:
        return caminho.resolve().relative_to(RAIZ).as_posix()
    except ValueError:
        return caminho.resolve().as_posix()


def _rotulo_quarto(e: EstadoQuadro) -> str:
    if not e.presente:
        return "ausente"
    lugar = "" if e.no_leito is None else ("no leito | " if e.no_leito else "fora do leito | ")
    return f"{lugar}tronco {e.inclinacao:.0f} graus"


def _rotulos_fisio(fisio: ResultadoFisioterapia, t_s: list[float]) -> list[str]:
    rotulos = []
    for t, a in zip(t_s, fisio.angulos):
        feitas = [r for r in fisio.repeticoes if r.fim_s <= t]
        incompletas = sum(not r.completa for r in feitas)
        angulo = "-" if a != a else f"{a:.0f}"  # a != a: NaN
        rotulos.append(f"{fisio.exercicio}: {len(feitas)} rep ({incompletas} incompletas) | angulo {angulo}")
    return rotulos


def processar(
    video: Path,
    cenario: Cenario,
    paciente_id: str,
    inicio: datetime,
    fps_alvo: float = 5.0,
    exercicio: str = "elevacao_lateral",
    saida: Path = CAMINHOS.resultados,
    usar_cache: bool = True,
    anotar: bool = True,
    cliente_llm: ClienteLLM | None = None,
) -> ResultadoSessao:
    video = Path(video)
    nome = video.stem
    cfg_inferencia = replace(ConfigInferencia(), fps_alvo=fps_alvo, dir_cache=saida / "cache_video")
    inferencia = analisar_video(video, cfg_inferencia, usar_cache)
    quadros = inferencia.quadros
    t_s = [q.t_s for q in quadros]

    fisio: ResultadoFisioterapia | None = None
    if cenario == "quarto":
        zona = estimar_zona(quadros, ConfigQuarto())
        pacientes = escolher_paciente(quadros, zona, ConfigPaciente())
        estados = calcular_estados(quadros, pacientes, zona)
        eventos_video = detectar_quedas(estados, paciente_id, inicio) + detectar_ausencia(estados, paciente_id, inicio)
        eventos_mov = movimentacao.detectar(estados, paciente_id, inicio, ConfigMovimentacao())
        rotulos = [_rotulo_quarto(e) for e in estados]
    else:
        zona = None
        pacientes = escolher_paciente(quadros, None, ConfigPaciente())
        fisio = analisar_fisioterapia(pacientes, t_s, paciente_id, inicio, ConfigFisioterapia(exercicio=exercicio))
        eventos_video, eventos_mov = fisio.eventos, []
        rotulos = _rotulos_fisio(fisio, t_s)

    video_anotado: Path | None = None
    if anotar and quadros:
        pasta = saida / "evidencias" / "video"
        video_anotado = pasta / f"{nome}_anotado.mp4"
        todos = eventos_video + eventos_mov
        marcas = [((e.instante - inicio).total_seconds(), e.tipo) for e in todos]
        recortes = gravar_anotado(video, fps_alvo, quadros, pacientes, zona, rotulos, marcas,
                                  video_anotado, pasta / nome)
        com_evidencia = {
            id(e): replace(e, evidencia={**e.evidencia, "video": relativo(video_anotado),
                                         **({"recorte": relativo(r)} if r else {})})
            for e, r in zip(todos, recortes)
        }
        eventos_video = [com_evidencia[id(e)] for e in eventos_video]
        eventos_mov = [com_evidencia[id(e)] for e in eventos_mov]

    pasta_eventos = saida / "eventos"
    salvar_jsonl(pasta_eventos / f"video_{paciente_id}.jsonl", eventos_video)
    if cenario == "quarto":
        salvar_jsonl(pasta_eventos / f"movimentacao_{paciente_id}.jsonl", eventos_mov)

    relatorio = saida / "relatorios" / f"{nome}.md"
    duracao = t_s[-1] + 1 / fps_alvo if t_s else 0.0
    dados = dados_da_sessao(nome, cenario, paciente_id, inicio, duracao, eventos_video + eventos_mov, fisio)
    redacao = escrever_relatorio(relatorio, dados, eventos_video + eventos_mov, cliente_llm or ClienteLLM(),
                                 relativo(video_anotado) if video_anotado else None, inferencia.s_por_quadro)
    return ResultadoSessao(eventos_video, eventos_mov, inferencia, fisio, video_anotado, relatorio, redacao.origem)
