"""Parâmetros do gerador de prescrições e das regras de anomalia."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ConfigGerador:
    inicio: datetime = datetime(2026, 11, 11, 8, 0, 0)  # primeiro dia da internação, 08:00
    medicamentos_por_paciente: int = 4  # cada um de uma classe diferente (rotina sem duplicidade)
    prob_ajuste: float = 0.15  # chance de um dia de rotina trazer ajuste de dose
    variacao_ajuste_max: float = 0.5  # ajuste de rotina muda a dose em no máximo 50%
    prob_suspensao_planejada: float = 0.3  # suspensão de rotina (contínuo com desmame antes)
    anomalias_por_paciente: int = 2  # tipos diferentes, em medicamentos diferentes
    horas_ate_anomalia: float = 6.0  # o item anômalo entra 6 h depois do item de rotina do dia


@dataclass(frozen=True)
class ConfigRegras:
    # dose_excessiva: nova dose ≥ 3× a anterior do mesmo medicamento. A rotina
    # muda no máximo 1,5×; triplicar de um dia para o outro é fora do padrão.
    fator_dose_excessiva: float = 3.0
    # Severidade MAXIMA: salto ≥ 5× a anterior, ou dose > 2× a máxima do catálogo.
    fator_maxima_anterior: float = 5.0
    fator_maxima_dose_max: float = 2.0
    # Tolerância relativa ao comparar a dose extraída do texto com a estruturada.
    tolerancia_dose: float = 1e-6


GERADOR = ConfigGerador()
REGRAS = ConfigRegras()
