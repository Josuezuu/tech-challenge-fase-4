"""Painel da central de monitoramento (RF-70, RF-71).

Uso: streamlit run app/painel.py

Lê só o que está em ``results/`` (gerado por ``python -m experiments.run_cenario``
e ``python -m experiments.run_avaliacao``); não processa mídia.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

RAIZ = Path(__file__).resolve().parents[1]
RESULTADOS = RAIZ / "results"

NIVEIS = {3: ("Crítico", "red"), 2: ("Atenção", "orange"), 1: ("Informativo", "blue")}
SEVERIDADES = {3: "máxima", 2: "alta", 1: "info"}
FONTES = {"video": "Vídeo", "movimentacao": "Movimentação", "audio": "Áudio",
          "sinais_vitais": "Sinais vitais", "prescricao": "Prescrição"}
VARIAVEIS = {"fc": "FC (bpm)", "spo2": "SpO2 (%)", "fr": "FR (rpm)", "pulso": "Pulso (bpm)", "pas": "PA sistólica"}
ORIGENS = {"real": "serviço real", "openai": "OpenAI (real)", "gravado": "resposta real gravada",
           "simulado": "modo simulado (sem chave)"}


# --- leitura -------------------------------------------------------------------------------------


def ler_json(caminho: Path) -> dict[str, Any] | None:
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def ler_jsonl(caminho: Path) -> list[dict[str, Any]]:
    try:
        with caminho.open(encoding="utf-8") as f:
            return [json.loads(linha) for linha in f if linha.strip()]
    except (OSError, ValueError):
        return []


def arquivo(relativo: str | None) -> Path | None:
    if not relativo:
        return None
    caminho = RAIZ / relativo
    return caminho if caminho.exists() else None


def eventos_do_paciente(pid: str) -> list[dict[str, Any]]:
    eventos: list[dict[str, Any]] = []
    for caminho in (RESULTADOS / "eventos").glob(f"*_{pid}.jsonl"):
        eventos.extend(ler_jsonl(caminho))
    return sorted(eventos, key=lambda e: e["instante"])


def hora(iso: str) -> str:
    return pd.Timestamp(iso).strftime("%d/%m %H:%M:%S")


# --- áreas ---------------------------------------------------------------------------------------


def area_alertas(alertas: list[dict[str, Any]]) -> None:
    if not alertas:
        st.info("Nenhum alerta para este paciente.")
        return
    for a in sorted(alertas, key=lambda x: x["instante"], reverse=True):
        nome, cor = NIVEIS[a["nivel"]]
        modalidades = ", ".join(a["modalidades"])
        with st.container(border=True):
            st.markdown(f":{cor}[**{nome}**] · {hora(a['instante'])} · regra `{a['regra']}` · {modalidades}")
            st.write(a["texto"])
            st.caption(f"Texto: {ORIGENS.get(a['texto_origem'], a['texto_origem'])}")
            with st.expander(f"{len(a['eventos'])} evento(s) e evidências"):
                for e in a["eventos"]:
                    st.markdown(f"- **{hora(e['instante'])}** · {FONTES.get(e['fonte'], e['fonte'])} · "
                                f"`{e['tipo']}` ({SEVERIDADES[e['severidade']]}): {e['descricao']}")
                    recorte = arquivo(e["evidencia"].get("recorte"))
                    if recorte:
                        st.image(str(recorte), width=320)


def area_sinais(pid: str, fonte: dict[str, Any], eventos: list[dict[str, Any]]) -> None:
    serie = arquivo(fonte.get("serie"))
    if serie is None:
        st.info(fonte.get("motivo") or "Sem série. Rode `python -m experiments.run_cenario`.")
        return
    df = pd.read_csv(serie, parse_dates=["instante"])
    variaveis = [v for v in ("spo2", "fc", "fr", "pas") if v in df.columns]
    longo = df.melt(id_vars=["instante"], value_vars=variaveis, var_name="variavel", value_name="valor")
    longo["variavel"] = longo["variavel"].map(VARIAVEIS)
    ev = pd.DataFrame([
        {"instante": pd.Timestamp(e["instante"]), "tipo": e["tipo"], "descricao": e["descricao"]}
        for e in eventos if e["fonte"] == "sinais_vitais"
    ])
    st.caption(f"Gravação {fonte.get('gravacao')} do BIDMC (PhysioNet), reproduzida como fluxo a 1 Hz. "
               f"Linhas vermelhas: eventos. Faixa cinza: anomalia plantada para avaliação.")
    inicio = df["instante"].min()
    plantadas = pd.DataFrame([
        {"de": inicio + pd.Timedelta(seconds=p["inicio_s"]), "ate": inicio + pd.Timedelta(seconds=p["fim_s"]),
         "tipo": p["tipo"]}
        for p in fonte.get("plantadas", [])
    ])
    for nome in longo["variavel"].unique():
        base = alt.Chart(longo[longo["variavel"] == nome]).mark_line().encode(
            x=alt.X("instante:T", title=None), y=alt.Y("valor:Q", title=nome, scale=alt.Scale(zero=False)),
        )
        camadas = [base]
        if not plantadas.empty:
            camadas.insert(0, alt.Chart(plantadas).mark_rect(opacity=0.15, color="gray").encode(
                x="de:T", x2="ate:T", tooltip=["tipo"]))
        if not ev.empty:
            camadas.append(alt.Chart(ev).mark_rule(color="red").encode(x="instante:T", tooltip=["tipo", "descricao"]))
        st.altair_chart(alt.layer(*camadas).properties(height=160), use_container_width=True)


def area_video(fonte: dict[str, Any], eventos: list[dict[str, Any]]) -> None:
    video = arquivo(fonte.get("video_navegador")) or arquivo(fonte.get("video_anotado"))
    if video is None:
        st.info(fonte.get("motivo") or "Sem vídeo processado.")
        return
    st.caption(f"Origem: `{fonte.get('arquivo')}` · cenário {fonte.get('cenario')} · "
               f"{fonte.get('s_por_quadro')} s por quadro em CPU (YOLOv8n-pose + YOLOv8n)")
    st.video(str(video))
    if fonte.get("fisioterapia"):
        f = fonte["fisioterapia"]
        c1, c2, c3 = st.columns(3)
        c1.metric("Repetições", f["repeticoes"])
        c2.metric("Incompletas", f["incompletas"])
        c3.metric("Amplitude média", "-" if f["amplitude_media"] is None else f"{f['amplitude_media']:.0f}°")
    do_video = [e for e in eventos if e["fonte"] in ("video", "movimentacao")]
    for e in do_video:
        st.markdown(f"- **{hora(e['instante'])}** `{e['tipo']}`: {e['descricao']}")
        recorte = arquivo(e["evidencia"].get("recorte"))
        if recorte:
            st.image(str(recorte), width=360)
    relatorio = arquivo(fonte.get("relatorio"))
    if relatorio:
        with st.expander("Relatório da sessão"):
            texto = relatorio.read_text(encoding="utf-8")
            st.markdown(re.sub(r"!\[[^\]]*\]\([^)]*\)", "", texto))  # imagens relativas não abrem aqui


def destacar(texto: str, trechos: list[str]) -> str:
    for t in sorted(set(trechos), key=len, reverse=True):
        texto = re.sub(re.escape(t), lambda m: f":red[**{m.group(0)}**]", texto, flags=re.IGNORECASE)
    return texto


def area_audio(fonte: dict[str, Any], eventos: list[dict[str, Any]]) -> None:
    analise = ler_json(arquivo(fonte.get("analise")) or Path("-"))
    if analise is None:
        st.info(fonte.get("motivo") or "Sem áudio processado.")
        return
    origens = analise.get("origens", {})
    st.caption(f"Origem: `{fonte.get('arquivo')}` · transcrição: {ORIGENS.get(origens.get('transcricao'), '-')} · "
               f"análise de texto: {ORIGENS.get(origens.get('analise'), '-')}")
    wav = arquivo(analise.get("wav"))
    if wav:
        st.audio(str(wav))
    termos = [e["evidencia"].get("trecho", "") for e in eventos if e["tipo"] == "termo_critico"]
    st.markdown("**Transcrição**")
    st.markdown(destacar(analise["transcricao"]["texto"], [t for t in termos if t]) or "_vazia_")
    frases = analise["analise"].get("frases", [])
    if frases:
        st.markdown("**Sentimento por frase** (Azure AI Language)")
        st.dataframe(pd.DataFrame(frases)[["texto", "sentimento", "positivo", "neutro", "negativo"]],
                     hide_index=True, use_container_width=True)
    entidades = analise["analise"].get("entidades", [])
    if entidades:
        st.markdown("**Entidades de saúde** (Text Analytics for health)")
        st.dataframe(pd.DataFrame(entidades)[["texto", "categoria", "negada", "confianca"]],
                     hide_index=True, use_container_width=True)
    comparacao = analise.get("comparacao_voz")
    if comparacao:
        st.markdown(f"**Voz × referência do paciente** (`{fonte.get('referencia')}`): "
                    f"{'**alteração**' if comparacao['alteracao'] else 'sem alteração'}")
        tabela = pd.DataFrame(comparacao["atributos"])[
            ["atributo", "media_referencia", "media_atual", "z", "piorou"]]
        st.dataframe(tabela, hide_index=True, use_container_width=True)
        st.caption("z = (atual − média da referência) / desvio da referência; alteração quando ≥ 2 atributos "
                   "pioram com |z| ≥ 2. Indica mudança em relação ao próprio paciente, não diagnóstico.")


def area_prescricoes(fonte: dict[str, Any], eventos: list[dict[str, Any]]) -> None:
    dados = ler_json(arquivo(fonte.get("prescricoes")) or Path("-"))
    if dados is None:
        st.info(fonte.get("motivo") or "Sem prescrições.")
        return
    st.caption(dados.get("aviso", "") + f" Extração do texto livre: {', '.join(fonte.get('origem_extracao', []))}.")
    itens = pd.DataFrame(dados["itens"])
    itens["instante"] = pd.to_datetime(itens["instante"])
    anomalos = {e["evidencia"].get("item_id"): e for e in eventos if e["fonte"] == "prescricao"}
    itens["anomalia"] = itens["id"].map(lambda i: anomalos[i]["tipo"] if i in anomalos else "rotina")
    grafico = alt.Chart(itens).mark_circle(size=90).encode(
        x=alt.X("instante:T", title=None),
        y=alt.Y("medicamento:N", title=None),
        color=alt.condition(alt.datum.anomalia != "rotina", alt.value("red"), alt.value("steelblue")),
        tooltip=["instante:T", "texto_livre", "dose", "unidade", "via", "acao", "anomalia"],
    ).properties(height=40 + 28 * itens["medicamento"].nunique())
    st.altair_chart(grafico, use_container_width=True)
    if anomalos:
        st.markdown("**Itens anômalos**")
        for e in anomalos.values():
            st.markdown(f"- **{hora(e['instante'])}** `{e['tipo']}`: {e['descricao']}")


def area_avaliacao() -> None:
    r = ler_json(RESULTADOS / "resultados.json")
    if r is None:
        st.info("Rode `python -m experiments.run_avaliacao` para gerar `results/resultados.json`.")
        return
    st.caption(f"Gerado em {r.get('gerado_em')} · versão {r.get('versao_git')}")
    linhas = []
    s = r.get("sinais", {})
    if s.get("status") == "ok":
        g = s["geral"]
        linhas.append(["Sinais vitais (BIDMC, anomalias plantadas)", g["recall"], g["precisao"], g["f1"],
                       f"atraso médio {g['atraso_medio_s']} s; {s['sem_plantio']['alertas_falsos_por_hora']} eventos/h sem plantio"])
    v = r.get("video", {})
    if v.get("status") == "ok":
        t = v["total"]
        linhas.append(["Vídeo (clipes anotados)", t.get("sensibilidade"), None, None,
                       f"{t.get('acertos')}/{t.get('esperados')} eventos, {t.get('falsos_positivos')} falsos positivos"])
    p = r.get("prescricoes", {})
    if p.get("status") == "ok":
        g = p["geral"]
        linhas.append(["Prescrições (sintéticas)", g["recall"], g["precisao"], g["f1"],
                       f"extração: {p['extracao']['acerto_item']} dos itens ({p['extracao']['origem']})"])
    a = r.get("audio", {})
    if a.get("status") == "ok":
        m = a["resumo"]
        linhas.append(["Áudio: termos críticos", m.get("termos_recall"), m.get("termos_precisao"), None,
                       f"alteração vocal certa em {m.get('acertos_alteracao')}/{m.get('pares_com_gabarito')} pares"
                       + (" (amostras sintéticas)" if m.get("so_amostras_sinteticas") else "")])
    if linhas:
        st.dataframe(pd.DataFrame(linhas, columns=["Fonte", "Recall", "Precisão", "F1", "Observação"]),
                     hide_index=True, use_container_width=True)
    c = r.get("cenario", {})
    if c.get("primeira_concordancia"):
        pc = c["primeira_concordancia"]
        st.markdown(f"**Cenário:** primeira concordância em {pc['paciente_id']} às {hora(pc['instante'])} "
                    f"({', '.join(pc['modalidades'])}), {pc['segundos_desde_primeiro_evento']:.0f} s depois do "
                    f"primeiro evento que ela reúne.")
    with st.expander("resultados.json completo"):
        st.json(r)


# --- página --------------------------------------------------------------------------------------


def reproduzir_cenario() -> None:
    with st.spinner("Rodando o cenário (sinais, vídeo, áudio, prescrições → alertas)..."):
        r = subprocess.run([sys.executable, "-m", "experiments.run_cenario"], cwd=RAIZ,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        st.sidebar.error(r.stderr[-800:] or "o cenário falhou")
    else:
        st.rerun()


def main() -> None:
    st.set_page_config(page_title="Monitoramento Multimodal", layout="wide")
    st.sidebar.title("Central de monitoramento")
    if st.sidebar.button("Reproduzir cenário", use_container_width=True):
        reproduzir_cenario()

    manifesto = ler_json(RESULTADOS / "cenario.json")
    alertas = ler_jsonl(RESULTADOS / "alertas.jsonl")
    if manifesto is None:
        st.title("Monitoramento multimodal de pacientes")
        st.info("Ainda não há resultados. Clique em **Reproduzir cenário** ou rode "
                "`python -m experiments.run_cenario`.")
        st.subheader("Avaliação")
        area_avaliacao()
        return

    pacientes = list(manifesto["pacientes"])
    pior = {pid: max((a["nivel"] for a in alertas if a["paciente_id"] == pid), default=0) for pid in pacientes}
    pacientes.sort(key=lambda pid: -pior[pid])

    def rotulo(pid: str) -> str:
        return f"{pid} · {NIVEIS[pior[pid]][0] if pior[pid] else 'sem alerta'}"

    pid = st.sidebar.radio("Pacientes", pacientes, format_func=rotulo)
    st.sidebar.caption(f"Cenário gerado em {manifesto['gerado_em']} · {manifesto['eventos']} eventos · "
                       f"{sum(manifesto['alertas'].values())} alertas")

    fontes = manifesto["pacientes"][pid]["fontes"]
    eventos = eventos_do_paciente(pid)
    alertas_pid = [a for a in alertas if a["paciente_id"] == pid]

    st.title(pid)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Críticos", sum(a["nivel"] == 3 for a in alertas_pid))
    c2.metric("Atenção", sum(a["nivel"] == 2 for a in alertas_pid))
    c3.metric("Informativos", sum(a["nivel"] == 1 for a in alertas_pid))
    c4.metric("Concordâncias", sum(a["regra"] == "concordancia" for a in alertas_pid))
    puladas = [f"{nome}: {f['motivo']}" for nome, f in fontes.items() if f["status"] != "ok"]
    if puladas:
        st.warning("Fontes não processadas — " + " · ".join(puladas))

    abas = st.tabs(["Alertas", "Sinais vitais", "Vídeo", "Áudio", "Prescrições", "Avaliação"])
    with abas[0]:
        area_alertas(alertas_pid)
    with abas[1]:
        area_sinais(pid, fontes.get("sinais", {}), eventos)
    with abas[2]:
        area_video(fontes.get("video", {}), eventos)
    with abas[3]:
        area_audio(fontes.get("audio", {}), eventos)
    with abas[4]:
        area_prescricoes(fontes.get("prescricoes", {}), eventos)
    with abas[5]:
        area_avaliacao()


main()
