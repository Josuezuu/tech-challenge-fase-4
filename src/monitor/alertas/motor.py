"""Motor de alertas com fusão por concordância de modalidades (RF-60, RF-61).

Cada evento recebido gera **no máximo um** alerta, pela regra de maior
prioridade que se aplica:

1. ``concordancia`` (CRÍTICO): evento ≥ ALTA e, na janela de 10 min para trás,
   eventos ≥ ALTA do mesmo paciente somam duas ou mais modalidades;
2. ``severidade_maxima`` (CRÍTICO): evento MAXIMA;
3. ``severidade_alta`` (ATENÇÃO): evento ALTA;
4. ``informativo`` (INFORMATIVO): evento INFO.

Repetição: depois de um alerta de concordância, outro só sai se entrar uma
modalidade nova ou a janela expirar; se a concordância não se aplica por isso,
o evento cai na regra seguinte. As outras regras respeitam um intervalo mínimo
por ``(paciente, tipo, nível)``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Iterable

from monitor.alertas.config import CONFIG, ConfigAlertas
from monitor.alertas.redacao import RedatorLLM, redigir_alerta
from monitor.eventos import Alerta, Evento, Modalidade, NivelAlerta, Severidade


@dataclass(frozen=True)
class _Concordancia:
    instante: datetime
    modalidades: frozenset[Modalidade]


def chave_ordem(evento: Evento) -> tuple[str, ...]:
    """Ordem total dos eventos: por instante e, no empate, por campos estáveis."""
    return (evento.instante.isoformat(), evento.paciente_id, evento.fonte.value, evento.tipo,
            str(int(evento.severidade)), evento.descricao)


def id_do_alerta(paciente_id: str, instante: datetime, regra: str, eventos: Iterable[Evento]) -> str:
    """Id determinístico: o mesmo alerta tem o mesmo id em qualquer execução."""
    base = "|".join([paciente_id, instante.isoformat(), regra, *("/".join(chave_ordem(e)) for e in eventos)])
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:12]


class MotorAlertas:
    def __init__(self, config: ConfigAlertas = CONFIG, cliente_llm: RedatorLLM | None = None) -> None:
        self.config = config
        self.cliente_llm = cliente_llm
        self._recentes: dict[str, list[Evento]] = {}  # eventos ≥ ALTA por paciente, dentro da janela
        self._concordancia: dict[str, _Concordancia] = {}
        self._ultimo: dict[tuple[str, str, NivelAlerta], datetime] = {}

    def processar(self, evento: Evento) -> list[Alerta]:
        """Recebe um evento (em ordem de instante) e devolve zero ou um alerta."""
        alerta = self._concordancia_de(evento) or self._por_severidade(evento)
        if evento.severidade >= Severidade.ALTA:
            self._recentes.setdefault(evento.paciente_id, []).append(evento)
        return [alerta] if alerta else []

    def processar_todos(self, eventos: Iterable[Evento]) -> list[Alerta]:
        alertas: list[Alerta] = []
        for evento in sorted(eventos, key=chave_ordem):
            alertas.extend(self.processar(evento))
        return alertas

    def _na_janela(self, evento: Evento) -> list[Evento]:
        janela = self.config.janela_concordancia_s
        recentes = [e for e in self._recentes.get(evento.paciente_id, [])
                    if 0 <= (evento.instante - e.instante).total_seconds() <= janela]
        self._recentes[evento.paciente_id] = recentes  # descarta o que já saiu da janela
        return recentes

    def _concordancia_de(self, evento: Evento) -> Alerta | None:
        recentes = self._na_janela(evento)
        if evento.severidade < Severidade.ALTA:
            return None
        envolvidos = [*recentes, evento]
        modalidades = frozenset(e.modalidade for e in envolvidos)
        if len(modalidades) < 2:
            return None
        anterior = self._concordancia.get(evento.paciente_id)
        if anterior is not None:
            ainda_na_janela = (evento.instante - anterior.instante).total_seconds() <= self.config.janela_concordancia_s
            if ainda_na_janela and modalidades <= anterior.modalidades:
                return None  # já avisado: nada de modalidade nova
        self._concordancia[evento.paciente_id] = _Concordancia(evento.instante, modalidades)
        return self._alerta(evento, NivelAlerta.CRITICO, "concordancia", envolvidos)

    def _por_severidade(self, evento: Evento) -> Alerta | None:
        if evento.severidade == Severidade.MAXIMA:
            nivel, regra = NivelAlerta.CRITICO, "severidade_maxima"
        elif evento.severidade == Severidade.ALTA:
            nivel, regra = NivelAlerta.ATENCAO, "severidade_alta"
        else:
            nivel, regra = NivelAlerta.INFORMATIVO, "informativo"
        chave = (evento.paciente_id, evento.tipo, nivel)
        ultimo = self._ultimo.get(chave)
        if ultimo is not None and (evento.instante - ultimo).total_seconds() < self.config.intervalo_minimo_s:
            return None
        self._ultimo[chave] = evento.instante
        return self._alerta(evento, nivel, regra, [evento])

    def _alerta(self, evento: Evento, nivel: NivelAlerta, regra: str, eventos: list[Evento]) -> Alerta:
        eventos_ordenados = tuple(sorted(eventos, key=chave_ordem))
        rascunho = Alerta(
            id=id_do_alerta(evento.paciente_id, evento.instante, regra, eventos_ordenados),
            paciente_id=evento.paciente_id,
            instante=evento.instante,
            nivel=nivel,
            regra=regra,
            eventos=eventos_ordenados,
            texto="",
            texto_origem="simulado",
        )
        texto, origem = redigir_alerta(rascunho, self.cliente_llm, self.config)
        return replace(rascunho, texto=texto, texto_origem=origem)
