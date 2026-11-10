"""Texto do alerta (RF-63): LLM com guarda, ou modelo fixo por regra.

A LLM só recebe os dados estruturados do alerta (nível, regra, eventos com
fonte, horário e descrição) — nunca mídia. Se o texto dela citar diagnóstico ou
conduta, ou passar do tamanho, vale o modelo fixo, que é determinístico.
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
    "(fonte, horário e descrição). Escreva de 2 a 3 frases curtas: diga o nível, cite a fonte "
    "e o horário de cada evento e descreva só o que foi observado. Não dê diagnóstico, não "
    "sugira hipótese de doença, medicação, dose ou conduta. Termine exatamente com a frase "
    "\"Avaliação da equipe necessária.\""
)

NOME_NIVEL = {NivelAlerta.CRITICO: "crítico", NivelAlerta.ATENCAO: "de atenção", NivelAlerta.INFORMATIVO: "informativo"}
NOME_FONTE = {
    "video": "vídeo", "movimentacao": "movimentação", "audio": "áudio",
    "sinais_vitais": "sinais vitais", "prescricao": "prescrição",
}
MOTIVO = {
    "concordancia": "por concordância entre {modalidades}",
    "severidade_maxima": "por evento de severidade máxima",
    "severidade_alta": "por evento de severidade alta",
    "informativo": "para registro",
}


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


def modelo_fixo(dados: dict[str, Any], config: ConfigAlertas = CONFIG) -> str:
    """Texto determinístico por regra: nível e motivo; eventos com fonte e horário; frase final."""
    nivel = NOME_NIVEL[NivelAlerta[dados["nivel"]]]
    motivo = MOTIVO.get(dados["regra"], "").format(modalidades=" e ".join(dados["modalidades"]))
    primeira = f"Alerta {nivel} para {dados['paciente']} {motivo}.".replace("  ", " ")
    eventos = dados["eventos"]
    citados = [f"{e['fonte']} às {e['horario']}: {e['descricao'].rstrip(' .')}" for e in eventos[: config.max_eventos_no_texto]]
    resto = len(eventos) - len(citados)
    segunda = "; ".join(citados) + (f"; e mais {resto} evento(s)" if resto > 0 else "")
    if not segunda.endswith((".", "!", "?", '."')):
        segunda += "."
    segunda = segunda[0].upper() + segunda[1:]
    return f"{primeira} {segunda} {config.frase_final}"


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
    redacao = cliente_llm.redigir(INSTRUCOES, dados, lambda d: modelo_fixo(d, config))
    if redacao.origem == "simulado" or not texto_aceito(redacao.texto, config):
        return fixo, "simulado"
    return redacao.texto.strip(), _origem_do_texto(redacao.origem)
