"""Prescrições sintéticas: rotina plausível + anomalias plantadas com rótulo (RF-50).

Rotina por paciente: 4 medicamentos de classes diferentes; cada um começa no
dia 0 ou 1 (``inicio``), tem um item por dia (``manutencao``), às vezes um
``ajuste`` de até 50% e, em ~30% dos casos, uma ``suspensao`` planejada — com
desmame (redução de dose na véspera) quando o medicamento é contínuo.

Anomalias (uma por item, cada uma num medicamento diferente do paciente):
- ``dose_excessiva``: item extra 6 h depois, com ≥ 3× a dose anterior;
- ``fora_da_faixa``: item extra acima da dose máxima ou abaixo da mínima do catálogo;
- ``suspensao_abrupta``: contínuo suspenso sem redução antes; os itens seguintes somem;
- ``duplicidade_classe``: início de outro medicamento da mesma classe de um ativo;
- ``via_incompativel``: um item de rotina passa para uma via fora das vias do catálogo.
"""

from __future__ import annotations

import math
import random
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Callable

from monitor.config import SEMENTE
from monitor.prescricoes.catalogo import CATALOGO, Medicamento
from monitor.prescricoes.config import GERADOR, ConfigGerador
from monitor.prescricoes.modelo import TIPOS_ANOMALIA, VIAS, ItemPrescricao, RotuloPrescricao

VIA_EXTENSO = {"IV": "endovenosa", "VO": "via oral", "SC": "subcutânea", "IM": "intramuscular", "INAL": "inalatória"}
PREFIXO = {"inicio": ("Iniciar ", ""), "manutencao": ("",), "ajuste": ("Ajustar: ", ""), "suspensao": ("Suspender: ",)}


# ---------------------------------------------------------------- texto livre

def _numero(x: float) -> str:
    return f"{x:g}".replace(".", ",")  # decimal com vírgula, como no prontuário


def _texto_dose(dose: float, unidade: str, rng: random.Random) -> str:
    if unidade == "mg" and dose >= 1000 and dose % 500 == 0 and rng.random() < 0.5:
        dose, unidade = dose / 1000, "g"
    return f"{_numero(dose)}{rng.choice([' ', ''])}{unidade}"


def _texto_frequencia(h: float, rng: random.Random) -> str:
    n = _numero(h)
    opcoes = [f"de {n}/{n}h", f"{n}/{n}h", f"a cada {n} horas", f"de {n} em {n} horas"]
    if h == 24:
        opcoes.append("uma vez ao dia")
    elif 24 % h == 0:
        vezes = int(24 // h)
        opcoes += [f"{vezes}x ao dia", f"{vezes} vezes ao dia"]
    return rng.choice(opcoes)


def texto_livre(item: ItemPrescricao, rng: random.Random) -> str:
    """Escreve o item como no prontuário, sorteando entre variações de escrita."""
    nome = rng.choice([item.medicamento.capitalize(), item.medicamento.upper(), item.medicamento])
    via = VIA_EXTENSO["INAL"] if item.via == "INAL" else rng.choice([item.via, VIA_EXTENSO[item.via]])
    dose = _texto_dose(item.dose, item.unidade, rng)
    freq = _texto_frequencia(item.intervalo_h, rng)
    corpo = rng.choice([f"{nome} {dose} {via} {freq}", f"{nome} {dose}, {via}, {freq}"])
    return rng.choice(PREFIXO[item.acao]) + corpo


# ---------------------------------------------------------------- rotina

class _Ids:
    def __init__(self) -> None:
        self.n = 0

    def novo(self) -> str:
        self.n += 1
        return f"tmp-{self.n}"


def _item(pid: str, instante: datetime, med: Medicamento, dose: float, via: str, acao: str,
          ids: _Ids, rng: random.Random) -> ItemPrescricao:
    item = ItemPrescricao(pid, instante, med.nome, float(dose), med.unidade, via, float(med.intervalo_h),
                          acao, "", ids.novo())  # type: ignore[arg-type]
    return replace(item, texto_livre=texto_livre(item, rng))


def _desmame(med: Medicamento, dose: float) -> float | None:
    """Maior dose usual entre 50% e 100% (exclusive) da atual; ``None`` se já está no mínimo."""
    menores = [d for d in med.doses_usuais if 0.5 * dose <= d < dose]
    return max(menores) if menores else None


def _escolher_medicamentos(rng: random.Random, k: int) -> list[Medicamento]:
    nomes = sorted(CATALOGO)
    rng.shuffle(nomes)
    escolhidos: list[Medicamento] = []
    for nome in nomes:
        if CATALOGO[nome].classe not in {m.classe for m in escolhidos}:
            escolhidos.append(CATALOGO[nome])
        if len(escolhidos) == k:
            break
    return escolhidos


def _rotina(pid: str, dias: int, inicio: datetime, rng: random.Random, ids: _Ids,
            cfg: ConfigGerador) -> list[ItemPrescricao]:
    itens: list[ItemPrescricao] = []
    for j, med in enumerate(_escolher_medicamentos(rng, cfg.medicamentos_por_paciente)):
        dia_ini = rng.choice([0, 1])
        dose = rng.choice(med.doses_usuais)
        via = rng.choice(med.vias)
        dia_susp = None
        if dias - dia_ini >= 5 and rng.random() < cfg.prob_suspensao_planejada:
            dia_susp = rng.randint(dia_ini + 3, dias - 1)
        for d in range(dia_ini, dias):
            instante = inicio + timedelta(days=d, minutes=30 * j)
            acao = "manutencao"
            if d == dia_ini:
                acao = "inicio"
            elif d == dia_susp:
                acao = "suspensao"
            elif dia_susp is not None and med.continuo and d == dia_susp - 1:
                reduzida = _desmame(med, dose)
                if reduzida is None:
                    dia_susp = None  # sem como reduzir: o contínuo segue até o fim
                else:
                    acao, dose = "ajuste", reduzida
            elif rng.random() < cfg.prob_ajuste:
                vizinhas = [x for x in med.doses_usuais
                            if x != dose and abs(x / dose - 1) <= cfg.variacao_ajuste_max]
                if vizinhas:
                    acao, dose = "ajuste", rng.choice(vizinhas)
            itens.append(_item(pid, instante, med, dose, via, acao, ids, rng))
            if acao == "suspensao":
                break
    return itens


# ---------------------------------------------------------------- anomalias

def _do_medicamento(itens: list[ItemPrescricao], nome: str) -> list[ItemPrescricao]:
    return sorted((i for i in itens if i.medicamento == nome), key=lambda i: i.instante)


def _vizinhos(itens: list[ItemPrescricao], base: ItemPrescricao) -> tuple[ItemPrescricao | None, ItemPrescricao | None]:
    hist = _do_medicamento(itens, base.medicamento)
    k = hist.index(base)
    return (hist[k - 1] if k > 0 else None), (hist[k + 1] if k + 1 < len(hist) else None)


def _passo(x: float) -> float:
    return 50.0 if x >= 200 else 5.0 if x >= 20 else 0.5 if x >= 2 else 0.1


def _para_cima(x: float) -> float:
    p = _passo(x)
    return round(math.ceil(x / p) * p, 6)


def _para_baixo(x: float) -> float:
    p = _passo(x)
    return round(math.floor(x / p) * p, 6)


Plantio = tuple[list[ItemPrescricao], ItemPrescricao] | None


def _bases(itens: list[ItemPrescricao], usados: set[str], rng: random.Random) -> list[ItemPrescricao]:
    """Itens de rotina (início/manutenção) cujo próximo item do medicamento, se houver, é manutenção.

    Assim o item anômalo não encosta num ajuste, desmame ou suspensão da rotina,
    e uma anomalia não cria outra por tabela."""
    bases = []
    for base in itens:
        if base.acao not in ("inicio", "manutencao") or base.medicamento in usados:
            continue
        _, depois = _vizinhos(itens, base)
        if depois is None or depois.acao == "manutencao":
            bases.append(base)
    rng.shuffle(bases)
    return bases


def _extra(base: ItemPrescricao, dose: float, ids: _Ids, rng: random.Random, cfg: ConfigGerador) -> ItemPrescricao:
    novo = replace(base, instante=base.instante + timedelta(hours=cfg.horas_ate_anomalia), dose=dose,
                   acao="ajuste", id=ids.novo())
    return replace(novo, texto_livre=texto_livre(novo, rng))


def _dose_excessiva(itens: list[ItemPrescricao], usados: set[str], ids: _Ids, rng: random.Random,
                    cfg: ConfigGerador) -> Plantio:
    for base in _bases(itens, usados, rng):
        novo = _extra(base, _para_cima(base.dose * rng.uniform(3.2, 6.0)), ids, rng, cfg)
        return [*itens, novo], novo
    return None


def _fora_da_faixa(itens: list[ItemPrescricao], usados: set[str], ids: _Ids, rng: random.Random,
                   cfg: ConfigGerador) -> Plantio:
    for base in _bases(itens, usados, rng):
        med = CATALOGO[base.medicamento]
        _, depois = _vizinhos(itens, base)
        acima = _para_cima(med.dose_max * rng.uniform(1.3, 1.9))
        abaixo = _para_baixo(med.dose_min * 0.5)
        opcoes = []
        if acima < 3 * base.dose:  # não pode virar dose_excessiva
            opcoes.append(acima)
        if abaixo > 0 and (depois is None or depois.dose < 3 * abaixo):  # a volta à rotina também não
            opcoes.append(abaixo)
        if opcoes:
            novo = _extra(base, rng.choice(opcoes), ids, rng, cfg)
            return [*itens, novo], novo
    return None


def _via_incompativel(itens: list[ItemPrescricao], usados: set[str], ids: _Ids, rng: random.Random,
                      cfg: ConfigGerador) -> Plantio:
    for base in _bases(itens, usados, rng):
        if base.acao != "manutencao":
            continue
        med = CATALOGO[base.medicamento]
        novo = replace(base, via=rng.choice([v for v in VIAS if v not in med.vias]))
        novo = replace(novo, texto_livre=texto_livre(novo, rng))
        return [novo if i is base else i for i in itens], novo
    return None


def _suspensao_abrupta(itens: list[ItemPrescricao], usados: set[str], ids: _Ids, rng: random.Random,
                       cfg: ConfigGerador) -> Plantio:
    for base in _bases(itens, usados, rng):
        antes, depois = _vizinhos(itens, base)
        if not CATALOGO[base.medicamento].continuo or depois is None:
            continue
        if antes is not None and base.dose < antes.dose:
            continue  # a véspera já foi redução: seria desmame
        novo = replace(_extra(base, base.dose, ids, rng, cfg), acao="suspensao")
        novo = replace(novo, texto_livre=texto_livre(novo, rng))
        restantes = [i for i in itens if not (i.medicamento == base.medicamento and i.instante > base.instante)]
        return [*restantes, novo], novo
    return None


def _duplicidade_classe(itens: list[ItemPrescricao], usados: set[str], ids: _Ids, rng: random.Random,
                        cfg: ConfigGerador) -> Plantio:
    presentes = {i.medicamento for i in itens}
    for base in _bases(itens, usados, rng):
        classe = CATALOGO[base.medicamento].classe
        outros = sorted(n for n, m in CATALOGO.items() if m.classe == classe and n not in presentes)
        if not outros:
            continue
        med = CATALOGO[rng.choice(outros)]
        instante = base.instante + timedelta(hours=cfg.horas_ate_anomalia)
        novo = _item(base.paciente_id, instante, med, rng.choice(med.doses_usuais), rng.choice(med.vias),
                     "inicio", ids, rng)
        usados.add(med.nome)
        return [*itens, novo], novo
    return None


PLANTADORES: dict[str, Callable[..., Plantio]] = {
    "dose_excessiva": _dose_excessiva,
    "fora_da_faixa": _fora_da_faixa,
    "suspensao_abrupta": _suspensao_abrupta,
    "duplicidade_classe": _duplicidade_classe,
    "via_incompativel": _via_incompativel,
}


# ---------------------------------------------------------------- entrada

def gerar(
    n_pacientes: int,
    dias: int,
    semente: int = SEMENTE,
    tipos: tuple[str, ...] = TIPOS_ANOMALIA,
    pacientes: list[str] | None = None,
    inicio: datetime | None = None,
    config: ConfigGerador = GERADOR,
) -> tuple[list[ItemPrescricao], list[RotuloPrescricao]]:
    """Gera itens e rótulos. ``tipos=()`` dá só rotina; um tipo só planta aquele tipo em cada paciente.

    ``pacientes`` dá os ids (o resto é ``paciente-NN``); ``inicio`` é o primeiro dia, 08:00 por padrão.
    """
    for tipo in tipos:
        if tipo not in PLANTADORES:
            raise ValueError(f"tipo de anomalia desconhecido: {tipo!r}")
    rng = random.Random(semente)
    inicio = inicio or config.inicio
    nomes = list(pacientes or [])
    nomes += [f"paciente-{i + 1:02d}" for i in range(len(nomes), n_pacientes)]
    todos: list[ItemPrescricao] = []
    rotulos: list[RotuloPrescricao] = []
    for p, pid in enumerate(nomes[:n_pacientes]):
        ids = _Ids()
        itens = _rotina(pid, dias, inicio, rng, ids, config)
        n = min(len(tipos), config.anomalias_por_paciente)
        escolhidos = [tipos[(p + k) % len(tipos)] for k in range(n)] if tipos else []
        usados: set[str] = set()
        anomalos: list[tuple[str, str]] = []
        for tipo in escolhidos:
            plantio = PLANTADORES[tipo](itens, usados, ids, rng, config)
            if plantio is None:
                continue  # rotina sem lugar para esse tipo (raro); fica sem esse rótulo
            itens, novo = plantio
            usados.add(novo.medicamento)
            anomalos.append((novo.id, tipo))
        # ids finais: paciente + ordem cronológica
        itens.sort(key=lambda i: (i.instante, i.medicamento))
        mapa = {i.id: f"{pid}-{k + 1:03d}" for k, i in enumerate(itens)}
        todos += [replace(i, id=mapa[i.id]) for i in itens]
        rotulos += [RotuloPrescricao(mapa[tmp], tipo, pid) for tmp, tipo in anomalos]
    return todos, rotulos
