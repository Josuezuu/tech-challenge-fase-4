"""Detectores de sinais vitais (RF-42..44, RF-46). Sem E/S: recebem ``Amostra``, devolvem ``Evento``.

Dois detectores olham cada amostra:

- ``DetectorLimiar``: o valor saiu da faixa clínica e ficou fora por N amostras.
- ``DetectorDesvio``: o valor se afastou muito da linha de base recente do
  próprio paciente (z-score robusto sobre os últimos 120 s), mesmo dentro da faixa.

Cada detector devolve uma ``Leitura`` por tipo de evento; o ``Supressor`` decide
se a leitura sustentada vira Evento ou se é repetição do mesmo episódio.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime

import numpy as np

from monitor.eventos import Evento, Fonte, Severidade
from monitor.sinais.config import CONFIG, ConfigSinais
from monitor.sinais.fluxo import Amostra, valido

FATOR_MAD = 1.4826  # MAD × 1,4826 estima o desvio-padrão quando o ruído é normal


@dataclass(frozen=True)
class Leitura:
    """O que um detector viu, nesta amostra, para um tipo de evento."""

    tipo: str  # ex.: spo2_baixa, fc_desvio
    variavel: str
    alterada: bool  # o valor desta amostra está fora do normal (sem exigir persistência)
    severidade: Severidade | None  # severidade já sustentada pela persistência; None = não dispara
    valor: float
    descricao: str
    detector: str


class _Contador:
    """Conta amostras seguidas em que uma condição vale; zera quando ela falha."""

    def __init__(self) -> None:
        self._seguidas: dict[str, int] = {}

    def contar(self, chave: str, condicao: bool) -> int:
        n = self._seguidas.get(chave, 0) + 1 if condicao else 0
        self._seguidas[chave] = n
        return n


def _nivel(valor: float, abaixo: bool, alta: float | None, maxima: float | None) -> Severidade | None:
    def passou(corte: float | None) -> bool:
        return corte is not None and (valor < corte if abaixo else valor > corte)

    if passou(maxima):
        return Severidade.MAXIMA
    if passou(alta):
        return Severidade.ALTA
    return None


class DetectorLimiar:
    """Faixa clínica por variável, com persistência mínima (RF-42)."""

    NOME = "limiar_clinico/v1"

    def __init__(self, config: ConfigSinais = CONFIG) -> None:
        self.config = config
        self._contador = _Contador()

    def ler(self, amostra: Amostra) -> list[Leitura]:
        leituras: list[Leitura] = []
        persistencia = self.config.persistencia_limiar
        for lim in self.config.limiares:
            valor = amostra.valores.get(lim.variavel)
            if not valido(valor):
                continue  # buraco na série: não conta nem zera a persistência
            assert valor is not None
            for abaixo, alta, maxima in ((True, lim.alta_abaixo, lim.maxima_abaixo),
                                         (False, lim.alta_acima, lim.maxima_acima)):
                if alta is None and maxima is None:
                    continue
                tipo = f"{lim.variavel}_{'baixa' if abaixo else 'alta'}"
                nivel = _nivel(valor, abaixo, alta, maxima)
                n_alta = self._contador.contar(f"{tipo}/alta", nivel is not None)
                n_maxima = self._contador.contar(f"{tipo}/maxima", nivel == Severidade.MAXIMA)
                if n_maxima >= persistencia:
                    severidade, corte, n = Severidade.MAXIMA, maxima, n_maxima
                elif n_alta >= persistencia:
                    severidade, corte, n = Severidade.ALTA, alta, n_alta
                else:
                    severidade, corte, n = None, None, 0
                descricao = ""
                if severidade is not None:
                    descricao = (f"{lim.nome} {valor:g} {lim.unidade}, {'abaixo' if abaixo else 'acima'} "
                                 f"de {corte:g} {lim.unidade} há {n} s")
                leituras.append(Leitura(tipo, lim.variavel, nivel is not None, severidade, valor, descricao, self.NOME))
        return leituras


class DetectorDesvio:
    """Desvio em relação ao próprio paciente: z-score robusto na janela passada (RF-43).

    ``z = (x - mediana) / max(1,4826 · MAD, escala_minima)``, com mediana e MAD
    dos últimos 120 s **antes** da amostra atual (é fluxo: não vê o futuro).

    Amostra fora da faixa clínica não é avaliada nem entra na linha de base:
    ali o limiar já fala, e a linha de base deve ser o normal do paciente —
    senão a volta ao normal depois de um episódio pareceria um desvio.
    """

    NOME = "desvio_paciente/v1"

    def __init__(self, config: ConfigSinais = CONFIG) -> None:
        self.config = config
        self._janelas: dict[str, deque[tuple[datetime, float]]] = {}
        self._contador = _Contador()

    def z_score(self, variavel: str, valor: float, instante: datetime) -> float | None:
        """z da amostra contra a janela passada; ``None`` se ainda há pouco histórico."""
        janela = self._janelas.setdefault(variavel, deque())
        while janela and (instante - janela[0][0]).total_seconds() > self.config.janela_desvio_s:
            janela.popleft()
        if len(janela) < self.config.minimo_amostras_desvio:
            return None
        historico = np.fromiter((v for _, v in janela), dtype=float, count=len(janela))
        mediana = float(np.median(historico))
        mad = float(np.median(np.abs(historico - mediana)))
        escala = max(FATOR_MAD * mad, self.config.escala_minima.get(variavel, 1e-6))
        return (valor - mediana) / escala

    def ler(self, amostra: Amostra, fora_da_faixa: frozenset[str] = frozenset()) -> list[Leitura]:
        """``fora_da_faixa``: variáveis que o limiar viu fora da faixa nesta amostra."""
        leituras: list[Leitura] = []
        for variavel in self.config.variaveis_desvio:
            valor = amostra.valores.get(variavel)
            if not valido(valor):
                continue
            assert valor is not None
            if variavel in fora_da_faixa:
                self._contador.contar(variavel, False)
                continue
            z = self.z_score(variavel, valor, amostra.instante)
            self._janelas[variavel].append((amostra.instante, valor))  # só entra depois de avaliada
            if variavel in self.config.desvio_so_para_baixo:
                alterada = z is not None and z < -self.config.z_desvio
            else:
                alterada = z is not None and abs(z) > self.config.z_desvio
            n = self._contador.contar(variavel, alterada)
            severidade = Severidade.ALTA if n >= self.config.persistencia_desvio else None
            descricao = ""
            if severidade is not None and z is not None:
                sentido = "acima" if z > 0 else "abaixo"
                descricao = (f"{variavel.upper()} {valor:g} muito {sentido} da linha de base do próprio "
                             f"paciente (z = {z:+.1f}) há {n} s")
            leituras.append(Leitura(f"{variavel}_desvio", variavel, alterada, severidade, valor, descricao, self.NOME))
        return leituras


@dataclass
class _EstadoSupressor:
    ultima_emissao: datetime
    severidade: Severidade
    normal_desde: datetime | None = None
    reaberto: bool = False


class Supressor:
    """Evita repetir o mesmo ``(paciente, tipo)`` (RF-44).

    Depois de emitir, um novo evento do mesmo tipo só passa se:
    - já se passaram ``supressao_s`` (300 s) desde o último (lembrete de episódio longo); ou
    - a variável ficou normal por ``normal_para_reabrir_s`` (30 s) seguidos (episódio novo); ou
    - a severidade subiu (ALTA → MAXIMA): escalada não pode ficar escondida.
    """

    def __init__(self, config: ConfigSinais = CONFIG) -> None:
        self.config = config
        self._estados: dict[tuple[str, str], _EstadoSupressor] = {}

    def observar(self, paciente_id: str, tipo: str, instante: datetime, alterada: bool) -> None:
        estado = self._estados.get((paciente_id, tipo))
        if estado is None:
            return
        if alterada:
            estado.normal_desde = None
            return
        if estado.normal_desde is None:
            estado.normal_desde = instante
        if (instante - estado.normal_desde).total_seconds() >= self.config.normal_para_reabrir_s:
            estado.reaberto = True

    def permitir(self, paciente_id: str, tipo: str, instante: datetime, severidade: Severidade) -> bool:
        chave = (paciente_id, tipo)
        estado = self._estados.get(chave)
        liberado = (
            estado is None
            or estado.reaberto
            or (instante - estado.ultima_emissao).total_seconds() >= self.config.supressao_s
            or severidade > estado.severidade
        )
        if liberado:
            self._estados[chave] = _EstadoSupressor(ultima_emissao=instante, severidade=severidade)
        return liberado


class MonitorVitais:
    """Junta limiar, desvio e supressor; um conjunto de detectores por paciente (RF-46).

    O desvio de uma variável não vira evento enquanto ela está fora da faixa
    clínica: aí o limiar já cobre, e o mesmo fato não sai duas vezes.

    ``sinteticas``: variáveis que não vêm do BIDMC (a PA sistólica sintética);
    os eventos delas levam ``evidencia["sintetica"] = "sim"`` (RF-47).
    """

    def __init__(
        self,
        config: ConfigSinais = CONFIG,
        gravacao: str = "",
        sinteticas: frozenset[str] = frozenset(),
        dir_evidencias: str = "results/evidencias/sinais",
    ) -> None:
        self.config = config
        self.gravacao = gravacao
        self.sinteticas = sinteticas
        self.dir_evidencias = dir_evidencias
        self.supressor = Supressor(config)
        self._detectores: dict[str, tuple[DetectorLimiar, DetectorDesvio]] = {}
        self.latencias_ms: list[float] = []

    @property
    def latencia_media_ms(self) -> float:
        return float(np.mean(self.latencias_ms)) if self.latencias_ms else 0.0

    def processar(self, amostra: Amostra) -> list[Evento]:
        inicio = time.perf_counter()
        if amostra.paciente_id not in self._detectores:
            self._detectores[amostra.paciente_id] = (DetectorLimiar(self.config), DetectorDesvio(self.config))
        limiar, desvio = self._detectores[amostra.paciente_id]
        leituras_limiar = limiar.ler(amostra)
        # O desvio existe para pegar o que o limiar não pega (mudança dentro da
        # faixa). Variável já fora da faixa nesta amostra: só o limiar fala.
        fora_da_faixa = frozenset(le.variavel for le in leituras_limiar if le.alterada)
        eventos: list[Evento] = []
        for leitura in leituras_limiar + desvio.ler(amostra, fora_da_faixa):
            self.supressor.observar(amostra.paciente_id, leitura.tipo, amostra.instante, leitura.alterada)
            if leitura.severidade is not None and self.supressor.permitir(
                amostra.paciente_id, leitura.tipo, amostra.instante, leitura.severidade
            ):
                eventos.append(self._evento(amostra, leitura))
        self.latencias_ms.append((time.perf_counter() - inicio) * 1000)
        return eventos

    def _evento(self, amostra: Amostra, leitura: Leitura) -> Evento:
        assert leitura.severidade is not None
        meia = self.config.meia_janela_evidencia_s
        t = amostra.t_s
        evidencia = {
            "gravacao": self.gravacao,
            "janela": f"{max(t - meia, 0):g}-{t + meia:g} s",
            "serie": f"{self.dir_evidencias}/{amostra.paciente_id}_{leitura.tipo}_{int(t)}.csv",
        }
        if leitura.variavel in self.sinteticas:
            evidencia["sintetica"] = "sim"
        return Evento(
            paciente_id=amostra.paciente_id,
            instante=amostra.instante,
            fonte=Fonte.SINAIS_VITAIS,
            tipo=leitura.tipo,
            severidade=leitura.severidade,
            descricao=leitura.descricao,
            detector=leitura.detector,
            valor=leitura.valor,
            evidencia=evidencia,
        )
