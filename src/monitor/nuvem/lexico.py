"""Léxico clínico mínimo usado pelo modo simulado da Azure AI Language.

Não substitui o Text Analytics for health: serve para o projeto rodar sem
chave e para os testes serem determinísticos. As categorias seguem os nomes
do Text Analytics for health (``SymptomOrSign``, ``MedicationName``...).
"""

from __future__ import annotations

import re
import unicodedata


def normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return sem_acento.lower()


SINTOMAS = [
    "falta de ar", "dificuldade para respirar", "dificuldade de respirar", "dor no peito",
    "dor toracica", "aperto no peito", "desmaio", "desmaiei", "tontura", "palpitacao",
    "palpitacoes", "cansaco", "fadiga", "fraqueza", "febre", "tosse", "chiado",
    "dor de cabeca", "confusao", "sonolencia", "nausea", "vomito", "dor", "inchaco",
    "formigamento", "dormencia", "fala enrolada", "visao turva", "sangramento",
]

DIAGNOSTICOS = [
    "pneumonia", "insuficiencia cardiaca", "hipertensao", "diabetes", "asma", "dpoc",
    "infarto", "avc", "sepse", "covid",
]

MEDICAMENTOS = [
    "dipirona", "paracetamol", "ibuprofeno", "cetoprofeno", "morfina", "tramadol",
    "losartana", "enalapril", "captopril", "furosemida", "hidroclorotiazida", "anlodipino",
    "metoprolol", "atenolol", "carvedilol", "enoxaparina", "heparina", "varfarina",
    "insulina", "metformina", "omeprazol", "ondansetrona", "ceftriaxona", "amoxicilina",
    "azitromicina", "vancomicina", "midazolam", "diazepam", "haloperidol", "prednisona",
    "dexametasona", "salbutamol", "amiodarona", "digoxina",
]

VIAS = {
    "iv": "IV", "ev": "IV", "intravenosa": "IV", "endovenosa": "IV", "vo": "VO", "oral": "VO",
    "via oral": "VO", "sc": "SC", "subcutanea": "SC", "im": "IM", "intramuscular": "IM",
    "inalatoria": "INAL",
}

POSITIVAS = ["melhor", "melhorou", "bem", "tranquilo", "otimo", "aliviado", "sem dor", "disposto"]
NEGATIVAS = [
    "pior", "piorou", "ruim", "mal", "cansado", "cansada", "medo", "preocupado", "preocupada",
    "angustia", "dor", "falta de ar", "nao consigo", "sofrendo", "fraco", "fraca", "exausto",
    "exausta",
]

NEGACOES = {"nao", "nega", "sem", "nenhum", "nenhuma", "nunca"}

RE_DOSE = re.compile(r"\b(\d+(?:[.,]\d+)?)\s*(mg|g|mcg|ml|ui|gotas|comprimidos?|cp)\b")
RE_FREQUENCIA = re.compile(
    r"\b(de\s+\d+\s*/\s*\d+\s*h|\d+\s*/\s*\d+\s*h|\d+\s*x\s*(?:ao|por)\s*dia|"
    r"\d+\s*vezes\s*(?:ao|por)\s*dia|uma vez ao dia|a cada\s+\d+\s*horas?)"
)


def _ocorrencias(norm: str, termos: list[str]) -> list[tuple[int, int, str]]:
    achados: list[tuple[int, int, str]] = []
    ocupados: list[tuple[int, int]] = []
    for termo in sorted(termos, key=len, reverse=True):
        for m in re.finditer(rf"\b{re.escape(termo)}\b", norm):
            if any(m.start() < f and m.end() > i for i, f in ocupados):
                continue
            ocupados.append((m.start(), m.end()))
            achados.append((m.start(), m.end(), termo))
    return sorted(achados)


def negado(norm: str, inicio: int) -> bool:
    anteriores = re.findall(r"\w+", norm[max(0, inicio - 30):inicio])[-3:]
    return any(p in NEGACOES for p in anteriores)


def entidades(texto: str) -> list[dict]:
    """Entidades no formato do Text Analytics for health (subconjunto).

    Os offsets valem para o texto em NFC (``normalizar`` preserva o
    comprimento de caracteres pré-compostos)."""
    texto = unicodedata.normalize("NFC", texto)
    norm = normalizar(texto)
    saida: list[dict] = []
    grupos = [(SINTOMAS, "SymptomOrSign"), (DIAGNOSTICOS, "Diagnosis"), (MEDICAMENTOS, "MedicationName")]
    for termos, categoria in grupos:
        for i, f, termo in _ocorrencias(norm, termos):
            saida.append(_entidade(texto, i, f, categoria, termo, negado(norm, i)))
    for m in RE_DOSE.finditer(norm):
        saida.append(_entidade(texto, m.start(), m.end(), "Dosage", None, False))
    for m in RE_FREQUENCIA.finditer(norm):
        saida.append(_entidade(texto, m.start(), m.end(), "Frequency", None, False))
    for i, f, termo in _ocorrencias(norm, list(VIAS)):
        saida.append(_entidade(texto, i, f, "MedicationRoute", VIAS[termo], False))
    return sorted(saida, key=lambda e: e["offset"])


def _entidade(texto: str, i: int, f: int, categoria: str, normalizado: str | None, negada: bool) -> dict:
    return {
        "texto": texto[i:f],
        "categoria": categoria,
        "offset": i,
        "comprimento": f - i,
        "confianca": 1.0,
        "normalizado": normalizado,
        "negada": negada,
    }


def sentimento(frase: str) -> tuple[str, float, float, float]:
    """Devolve (rótulo, positivo, neutro, negativo) por contagem de léxico."""
    norm = normalizar(frase)
    pos = len(_ocorrencias(norm, POSITIVAS))
    neg = sum(1 for i, _f, _t in _ocorrencias(norm, NEGATIVAS) if not negado(norm, i))
    if pos == neg == 0:
        return "neutral", 0.1, 0.8, 0.1
    total = pos + neg
    p, n = pos / total * 0.9, neg / total * 0.9
    rotulo = "positive" if pos > neg else "negative" if neg > pos else "mixed"
    return rotulo, round(p, 3), 0.1, round(n, 3)
