"""Texto do alerta (RF-63): LLM com guarda, ou modelo fixo por regra.

Todo alerta tem o mesmo formato: ``<cabeçalho> <descrição> <frase final>``.
O cabeçalho ("Alerta CRÍTICO · leito-12 · concordância entre áudio e vídeo.")
e a frase final são montados pelo código; a LLM escreve só a descrição do que
foi observado. Assim o nível e o paciente aparecem sempre no mesmo lugar.

A LLM só recebe os dados estruturados do alerta (nível, regra, eventos com
fonte, horário e descrição) — nunca mídia. Se a descrição dela citar
diagnóstico ou conduta, repetir o cabeçalho ou passar do tamanho, vale o modelo
fixo, que é determinístico.
"""

from __future__ import annotations

from typing import Any, Protocol

from monitor.alertas.config import CONFIG, ConfigAlertas
from monitor.eventos import Alerta, NivelAlerta
from monitor.nuvem.gravacao import Origem
from monitor.nuvem.lexico import normalizar
from monitor.nuvem.openai_llm import Redacao

INSTRUCOES = (
    "Você redige alertas para a equipe de enfermagem de um hospital, em português do Brasil. "
    "Recebe um JSON com o nível do alerta, a regra que o disparou e os eventos observados "
    "(fonte, horário e descrição). O sistema já põe um cabeçalho com o nível, o paciente e a "
    "regra, e uma frase final: escreva só o corpo, em 1 ou 2 frases curtas, descrevendo o que "
    "foi observado em cada evento, com a fonte e o horário. Não repita o nível, o paciente nem "
    "a regra; não comece com \"Alerta\", \"Nível\" ou \"Fonte\"; não escreva frase de "
    "encerramento. Não dê diagnóstico, não sugira hipótese de doença, medicação, dose ou conduta."
)

ROTULO_NIVEL = {NivelAlerta.CRITICO: "CRÍTICO", NivelAlerta.ATENCAO: "ATENÇÃO", NivelAlerta.INFORMATIVO: "INFORMATIVO"}
NOME_FONTE = {
    "video": "vídeo", "movimentacao": "movimentação", "audio": "áudio",
    "sinais_vitais": "sinais vitais", "prescricao": "prescrição",
}
MOTIVO = {
    "concordancia": "concordância entre {modalidades}",
    "severidade_maxima": "evento de severidade máxima",
    "severidade_alta": "evento de severidade alta",
    "informativo": "registro",
}
INICIOS_PROIBIDOS = ("alerta", "nivel", "fonte")  # o corpo não repete o cabeçalho


class RedatorLLM(Protocol):
    def redigir(self, instrucoes: str, dados: dict[str, Any], modelo_fixo: Any, max_tokens: int = 400) -> Redacao: ...


def dados_do_alerta(alerta: Alerta) -> dict[str, Any]:
    """O que a LLM (e o modelo fixo) recebem: só dados estruturados."""
    return {
        "paciente": alerta.paciente_id,
        "nivel": alerta.nivel.name,
        "regra": alerta.regra,
        "modalidades": [NOME_FONTE.get(m, m) for m in alerta.modalidades],
        "eventos": [
            {
                "fonte": NOME_FONTE.get(e.fonte.value, e.fonte.value),
                "horario": e.instante.strftime("%H:%M:%S"),
                "tipo": e.tipo,
                "severidade": e.severidade.name,
                "descricao": e.descricao,
            }
            for e in alerta.eventos
        ],
    }


def cabecalho(dados: dict[str, Any]) -> str:
    """Primeira frase, igual em todo alerta: ``Alerta <NÍVEL> · <paciente> · <motivo>.``"""
    nivel = ROTULO_NIVEL[NivelAlerta[dados["nivel"]]]
    partes = [f"Alerta {nivel}", dados["paciente"]]
    fontes = dados["modalidades"]
    lista = ", ".join(fontes[:-1]) + " e " + fontes[-1] if len(fontes) > 1 else "".join(fontes)
    motivo = MOTIVO.get(dados["regra"], "").format(modalidades=lista)
    if motivo:
        partes.append(motivo)
    return " · ".join(partes) + "."


def corpo_fixo(dados: dict[str, Any], config: ConfigAlertas = CONFIG) -> str:
    """Eventos com fonte, horário e descrição (até ``max_eventos_no_texto``; o resto é contado)."""
    eventos = dados["eventos"]
    citados = [f"{e['fonte']} às {e['horario']}: {e['descricao'].rstrip(' .')}" for e in eventos[: config.max_eventos_no_texto]]
    resto = len(eventos) - len(citados)
    corpo = "; ".join(citados) + (f"; e mais {resto} evento(s)" if resto > 0 else "")
    if not corpo.endswith((".", "!", "?", '."')):
        corpo += "."
    return corpo[0].upper() + corpo[1:]


def montar(dados: dict[str, Any], corpo: str, config: ConfigAlertas = CONFIG) -> str:
    return f"{cabecalho(dados)} {corpo} {config.frase_final}"


def modelo_fixo(dados: dict[str, Any], config: ConfigAlertas = CONFIG) -> str:
    """Texto determinístico: cabeçalho, eventos com fonte e horário, frase final."""
    return montar(dados, corpo_fixo(dados, config), config)


def limpar_corpo(texto: str, config: ConfigAlertas = CONFIG) -> str | None:
    """Corpo escrito pela LLM, sem a frase final; None se ele repetir o cabeçalho."""
    corpo = texto.replace(config.frase_final, "").strip()
    if normalizar(corpo).startswith(INICIOS_PROIBIDOS):
        return None
    return corpo


def termo_proibido(texto: str, config: ConfigAlertas = CONFIG) -> str | None:
    norm = normalizar(texto)
    return next((t for t in config.termos_proibidos if t in norm), None)


def texto_aceito(texto: str, config: ConfigAlertas = CONFIG) -> bool:
    """Guarda: texto não vazio, até ``max_caracteres`` e sem termo proibido."""
    return bool(texto.strip()) and len(texto) <= config.max_caracteres and termo_proibido(texto, config) is None


def _origem_do_texto(origem: Origem) -> str:
    return "openai" if origem == "real" else origem  # o Alerta usa "openai" | "gravado" | "simulado"


def redigir_alerta(
    alerta: Alerta,
    cliente_llm: RedatorLLM | None,
    config: ConfigAlertas = CONFIG,
) -> tuple[str, str]:
    """Devolve ``(texto, origem)``. Sem cliente, ou se a guarda reprovar, usa o modelo fixo (``"simulado"``)."""
    dados = dados_do_alerta(alerta)
    fixo = modelo_fixo(dados, config)
    if cliente_llm is None:
        return fixo, "simulado"
    redacao = cliente_llm.redigir(INSTRUCOES, dados, lambda d: corpo_fixo(d, config))
    if redacao.origem == "simulado":
        return fixo, "simulado"
    corpo = limpar_corpo(redacao.texto, config)
    if not corpo:
        return fixo, "simulado"
    texto = montar(dados, corpo, config)
    if not texto_aceito(texto, config):
        return fixo, "simulado"
    return texto, _origem_do_texto(redacao.origem)
