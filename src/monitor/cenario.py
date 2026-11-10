"""Cenário de ponta a ponta (RF-69, RF-71).

Lê ``data/cenario.json``, roda cada fonte de cada paciente, passa todos os
Eventos pelo motor de alertas e grava:

- ``results/eventos/<fonte>_<paciente>.jsonl`` e ``results/alertas.jsonl``;
- os artefatos que o painel mostra (série dos sinais, vídeo anotado,
  relatório da sessão, análise do áudio, prescrições);
- ``results/cenario.json``: o manifesto, com o que rodou, o que foi pulado
  e por quê, e a latência até o primeiro alerta crítico.

Fonte cujo arquivo não existe é **pulada com aviso**, nunca derruba o cenário:
enquanto as gravações do grupo não chegam, o cenário roda com o que há.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from monitor.alertas.avaliacao import latencia_ponta_a_ponta
from monitor.alertas.motor import MotorAlertas
from monitor.alertas.saida import gravar_alertas
from monitor.config import CAMINHOS, SEMENTE
from monitor.eventos import Alerta, Evento, Fonte, NivelAlerta, salvar_jsonl
from monitor.nuvem.openai_llm import ClienteLLM

log = logging.getLogger(__name__)

CENARIO_PADRAO = CAMINHOS.dados / "cenario.json"


def relativo(caminho: Path) -> str:
    try:
        return caminho.resolve().relative_to(CAMINHOS.raiz.resolve()).as_posix()
    except ValueError:
        return caminho.resolve().as_posix()


def primeiro_existente(arquivos: str | list[str], raiz: Path) -> Path | None:
    """O primeiro caminho da lista que existe (ex.: a gravação do grupo, senão o clipe público)."""
    for a in [arquivos] if isinstance(arquivos, str) else arquivos:
        caminho = raiz / a
        if caminho.exists():
            return caminho
    return None


@dataclass
class ResultadoFonte:
    status: str  # "ok" | "pulada" | "erro"
    eventos: list[Evento] = field(default_factory=list)
    artefatos: dict[str, Any] = field(default_factory=dict)
    motivo: str | None = None

    def resumo(self) -> dict[str, Any]:
        return {"status": self.status, "eventos": len(self.eventos), "motivo": self.motivo, **self.artefatos}


# --- fontes -------------------------------------------------------------------------------------


def rodar_sinais(pid: str, cfg: dict[str, Any], saida: Path) -> ResultadoFonte:
    from monitor.sinais import bidmc
    from monitor.sinais.detectores import MonitorVitais
    from monitor.sinais.evidencia import gravar_evidencia, gravar_serie
    from monitor.sinais.fluxo import reproduzir
    from monitor.sinais.injecao import TIPOS, Especificacao, plantar

    nr = int(cfg.get("gravacao", 1))
    if not bidmc.arquivo_bidmc(nr).exists():
        return ResultadoFonte("pulada", motivo="BIDMC não baixado: python scripts/baixar_bidmc.py")
    inicio = datetime.fromisoformat(cfg["inicio"])
    df = bidmc.carregar(nr)
    especificacoes = []
    for texto in cfg.get("plantar", []):
        tipo, _, resto = texto.partition("@")
        t0, _, duracao = resto.partition(":")
        if tipo not in TIPOS:
            raise ValueError(f"tipo de anomalia desconhecido no cenário: {tipo!r}")
        especificacoes.append(Especificacao(tipo, float(t0), float(duracao or 60)))
    rotulos = []
    if especificacoes:
        df, rotulos = plantar(df, especificacoes, SEMENTE)

    monitor = MonitorVitais(gravacao=bidmc.nome_gravacao(nr))
    eventos: list[Evento] = []
    for amostra in reproduzir(df, pid, inicio):
        eventos.extend(monitor.processar(amostra))
    for e in eventos:
        gravar_evidencia(df, e, inicio)
    serie = gravar_serie(df, inicio, saida / "series" / f"sinais_vitais_{pid}.csv")
    return ResultadoFonte("ok", eventos, {
        "gravacao": bidmc.nome_gravacao(nr),
        "serie": relativo(serie),
        "plantadas": [r.to_dict() for r in rotulos],
        "latencia_media_ms": round(monitor.latencia_media_ms, 4),
    })


def para_h264(origem: Path) -> Path:
    """Recodifica o vídeo anotado (mp4v do OpenCV, que o navegador não toca) em H.264 para o painel."""
    import subprocess

    import imageio_ffmpeg

    destino = origem.with_name(f"{origem.stem}_h264.mp4")
    if destino.exists() and destino.stat().st_mtime >= origem.stat().st_mtime:
        return destino
    subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(origem),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(destino)],
        check=True, timeout=600,
    )
    return destino


def rodar_video(pid: str, cfg: dict[str, Any], saida: Path) -> ResultadoFonte:
    video = primeiro_existente(cfg["arquivo"], CAMINHOS.raiz)
    if video is None:
        return ResultadoFonte("pulada", motivo=f"nenhum vídeo encontrado entre {cfg['arquivo']}")
    from monitor.video.pipeline import processar

    r = processar(video, cfg.get("cenario", "quarto"), pid, datetime.fromisoformat(cfg["inicio"]),
                  fps_alvo=float(cfg.get("fps", 5)), exercicio=cfg.get("exercicio", "elevacao_lateral"), saida=saida)
    artefatos: dict[str, Any] = {
        "arquivo": relativo(video),
        "cenario": cfg.get("cenario", "quarto"),
        "s_por_quadro": round(r.inferencia.s_por_quadro, 3),
        "video_anotado": relativo(r.video_anotado) if r.video_anotado else None,
        "video_navegador": relativo(para_h264(r.video_anotado)) if r.video_anotado else None,
        "relatorio": relativo(r.relatorio) if r.relatorio else None,
    }
    if r.fisio is not None:
        artefatos["fisioterapia"] = {"repeticoes": r.fisio.total, "incompletas": r.fisio.incompletas,
                                     "amplitude_media": r.fisio.amplitude_media}
    return ResultadoFonte("ok", r.eventos, artefatos)


def rodar_audio(pid: str, cfg: dict[str, Any], saida: Path) -> ResultadoFonte:
    audio = primeiro_existente(cfg["arquivo"], CAMINHOS.raiz)
    if audio is None:
        return ResultadoFonte("pulada", motivo=f"nenhum áudio encontrado entre {cfg['arquivo']}")
    referencia = primeiro_existente(cfg["referencia"], CAMINHOS.raiz) if cfg.get("referencia") else None
    from monitor.audio.fluxo import processar

    r = processar(audio, pid, datetime.fromisoformat(cfg["inicio"]), referencia,
                  whisper=bool(cfg.get("whisper", False)), dir_saida=saida / "audio")
    destino = saida / "audio" / f"{pid}_{audio.stem}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(r.to_dict(), ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return ResultadoFonte("ok", list(r.eventos), {
        "arquivo": relativo(audio),
        "referencia": relativo(referencia) if referencia else None,
        "analise": relativo(destino),
        "origens": {"transcricao": r.transcricao.origem, "analise": r.analise.origem},
    })


def rodar_prescricoes(pid: str, cfg: dict[str, Any], saida: Path) -> ResultadoFonte:
    from monitor.nuvem.azure_linguagem import ClienteLinguagem
    from monitor.prescricoes.avaliacao import extrair_todos
    from monitor.prescricoes.gerador import gerar
    from monitor.prescricoes.regras import avaliar as aplicar_regras

    itens, rotulos = gerar(1, int(cfg.get("dias", 5)), int(cfg.get("semente", SEMENTE)), pacientes=[pid],
                           inicio=datetime.fromisoformat(cfg["inicio"]))
    extracoes = extrair_todos(itens, ClienteLinguagem())
    eventos = aplicar_regras(itens, extracoes)
    destino = saida / "prescricoes" / f"{pid}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps({
        "aviso": "Dados sintéticos e catálogo didático; não são referência clínica.",
        "itens": [i.to_dict() for i in itens],
        "rotulos": [r.to_dict() for r in rotulos],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return ResultadoFonte("ok", eventos, {
        "prescricoes": relativo(destino),
        "itens": len(itens),
        "origem_extracao": sorted({x.origem for x in extracoes.values()}),
    })


FONTES: dict[str, Callable[[str, dict[str, Any], Path], ResultadoFonte]] = {
    "sinais": rodar_sinais,
    "video": rodar_video,
    "audio": rodar_audio,
    "prescricoes": rodar_prescricoes,
}

ARQUIVO_EVENTOS = {
    Fonte.SINAIS_VITAIS: "sinais_vitais",
    Fonte.VIDEO: "video",
    Fonte.MOVIMENTACAO: "movimentacao",
    Fonte.AUDIO: "audio",
    Fonte.PRESCRICAO: "prescricao",
}


# --- orquestração -------------------------------------------------------------------------------


def limpar(saida: Path) -> None:
    """Apaga eventos e alertas da execução anterior (artefatos de mídia ficam, o cache do vídeo também)."""
    for arquivo in (saida / "eventos").glob("*.jsonl"):
        arquivo.unlink()
    (saida / "alertas.jsonl").unlink(missing_ok=True)


def primeiro_alerta(alertas: list[Alerta], regra: str | None = None) -> dict[str, Any] | None:
    """O primeiro alerta crítico (de uma regra, se dada) e quanto tempo depois do
    primeiro evento que ele reúne ele saiu (RF-69)."""
    criticos = [a for a in alertas if a.nivel == NivelAlerta.CRITICO and (regra is None or a.regra == regra)]
    if not criticos:
        return None
    a = min(criticos, key=lambda x: x.instante)
    return {
        "paciente_id": a.paciente_id,
        "instante": a.instante.isoformat(),
        "regra": a.regra,
        "modalidades": a.modalidades,
        "segundos_desde_primeiro_evento": latencia_ponta_a_ponta(a),
    }


def executar(
    cenario: dict[str, Any],
    saida: Path = CAMINHOS.resultados,
    cliente_llm: ClienteLLM | None = None,
    fontes: dict[str, Callable[[str, dict[str, Any], Path], ResultadoFonte]] = FONTES,
) -> dict[str, Any]:
    limpar(saida)
    todos: list[Evento] = []
    manifesto: dict[str, Any] = {"gerado_em": datetime.now().isoformat(timespec="seconds"), "pacientes": {}}

    for paciente in cenario["pacientes"]:
        pid = paciente["paciente_id"]
        resumo: dict[str, Any] = {}
        for nome, rodar in fontes.items():
            if nome not in paciente:
                continue
            try:
                r = rodar(pid, paciente[nome], saida)
            except Exception as erro:  # noqa: BLE001 — uma fonte com defeito não derruba as outras
                log.exception("fonte %s do paciente %s falhou", nome, pid)
                r = ResultadoFonte("erro", motivo=f"{type(erro).__name__}: {erro}")
            if r.status == "pulada":
                log.warning("%s/%s pulada: %s", pid, nome, r.motivo)
            resumo[nome] = r.resumo()
            todos.extend(r.eventos)
        manifesto["pacientes"][pid] = {"fontes": resumo}

    por_arquivo: dict[str, list[Evento]] = {}
    for e in todos:
        por_arquivo.setdefault(f"{ARQUIVO_EVENTOS[e.fonte]}_{e.paciente_id}", []).append(e)
    for nome, eventos in por_arquivo.items():
        salvar_jsonl(saida / "eventos" / f"{nome}.jsonl", sorted(eventos, key=lambda e: e.instante))

    motor = MotorAlertas(cliente_llm=cliente_llm if cliente_llm is not None else ClienteLLM())
    alertas = motor.processar_todos(todos)
    gravar_alertas(alertas, saida / "alertas.jsonl")

    manifesto["eventos"] = len(todos)
    manifesto["alertas"] = {n.name: sum(a.nivel == n for a in alertas) for n in NivelAlerta}
    manifesto["concordancias"] = sum(a.regra == "concordancia" for a in alertas)
    manifesto["primeiro_critico"] = primeiro_alerta(alertas)
    manifesto["primeira_concordancia"] = primeiro_alerta(alertas, "concordancia")
    manifesto["texto_alertas_origem"] = sorted({a.texto_origem for a in alertas})
    (saida / "cenario.json").write_text(json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifesto


def carregar(caminho: Path = CENARIO_PADRAO) -> dict[str, Any]:
    return json.loads(Path(caminho).read_text(encoding="utf-8"))
