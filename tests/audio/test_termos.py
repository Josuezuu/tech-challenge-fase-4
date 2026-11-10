from datetime import datetime, timedelta

import pytest

from monitor.audio.termos import detectar
from monitor.config import Credenciais
from monitor.eventos import Severidade
from monitor.nuvem.azure_fala import Palavra, Transcricao
from monitor.nuvem.azure_linguagem import AnaliseTexto, ClienteLinguagem, EntidadeSaude, FraseSentimento
from monitor.nuvem.gravacao import Gravador

INICIO = datetime(2026, 11, 13, 9, 0, 0)
SEM_CHAVE = Credenciais(None, None, None, None, None, "gpt-4o-mini")


def transcricao_de(texto: str, passo_s: float = 0.5) -> Transcricao:
    """Uma palavra a cada ``passo_s`` segundos, uma por token do texto."""
    tokens = texto.split()
    palavras = tuple(Palavra(t.strip(".,!?"), i * passo_s, (i + 1) * passo_s) for i, t in enumerate(tokens))
    return Transcricao(texto, palavras, "pt-BR", len(tokens) * passo_s, "azure", "simulado")


def analise_vazia(frases: tuple[FraseSentimento, ...] = (), entidades: tuple[EntidadeSaude, ...] = ()) -> AnaliseTexto:
    return AnaliseTexto("neutral", frases, (), entidades, "simulado")


def do_tipo(eventos, tipo):
    return [e for e in eventos if e.tipo == tipo]


def test_aceite_febre_negada_e_falta_de_ar(tmp_path):
    texto = "Não tenho febre, mas estou com falta de ar"
    analise = ClienteLinguagem(SEM_CHAVE, "simulado", Gravador("l", tmp_path)).analisar(texto)
    eventos = detectar(analise, transcricao_de(texto), "leito-12", INICIO)

    termos = do_tipo(eventos, "termo_critico")
    assert len(termos) == 1
    e = termos[0]
    assert e.severidade == Severidade.ALTA
    assert e.evidencia["termo"] == "falta de ar"
    assert e.evidencia["fonte_termo"] == "entidade"
    # "falta" é a 7.ª palavra: começa em 6 × 0,5 s
    assert e.instante == INICIO + timedelta(seconds=3.0)
    assert not any("febre" in ev.evidencia.get("termo", "") for ev in eventos)


def test_termo_que_o_azure_nao_marcou_vem_da_lista():
    texto = "Hoje deu uma tontura forte"
    eventos = detectar(analise_vazia(), transcricao_de(texto), "p", INICIO)
    assert len(eventos) == 1
    assert eventos[0].evidencia["fonte_termo"] == "lista"
    assert eventos[0].severidade == Severidade.INFO
    assert eventos[0].instante == INICIO + timedelta(seconds=1.5)


def test_negacao_vale_para_a_lista_e_para_o_azure():
    texto = "Não sinto tontura. Teve febre ontem"
    febre_negada = EntidadeSaude("febre", "SymptomOrSign", texto.index("febre"), 5, 0.9, None, True)
    eventos = detectar(analise_vazia(entidades=(febre_negada,)), transcricao_de(texto), "p", INICIO)
    assert eventos == []


def test_instante_casa_palavras_desalinhadas_do_texto():
    # O Azure real devolve palavras léxicas: sem pontuação e com número por extenso.
    texto = "Há 2 dias senti dor no peito. E hoje dor no peito de novo."
    palavras_texto = "há dois dias senti dor no peito e hoje dor no peito de novo".split()
    palavras = tuple(Palavra(p, float(i), float(i + 1)) for i, p in enumerate(palavras_texto))
    t = Transcricao(texto, palavras, "pt-BR", 14.0, "azure", "real")
    eventos = detectar(analise_vazia(), t, "p", INICIO)
    assert len(eventos) == 1
    assert eventos[0].instante == INICIO + timedelta(seconds=4)  # "dor" é a 5.ª palavra
    assert eventos[0].evidencia["ocorrencias"] == "2"


def test_sentimento_negativo_acima_do_limiar():
    texto = "Estou muito mal. Dormi pouco."
    frases = (
        FraseSentimento("Estou muito mal.", "negative", 0.05, 0.05, 0.9, 0),
        FraseSentimento("Dormi pouco.", "negative", 0.1, 0.2, 0.7, 17),
    )
    eventos = detectar(analise_vazia(frases=frases), transcricao_de(texto), "p", INICIO)
    assert [e.tipo for e in eventos] == ["sentimento_negativo"]
    assert eventos[0].valor == pytest.approx(0.9)
    assert eventos[0].instante == INICIO
