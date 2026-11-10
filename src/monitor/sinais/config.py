"""Parâmetros dos detectores de sinais vitais.

Origem das faixas: os escores de alerta precoce do tipo NEWS2 (Royal College
of Physicians, 2017) pontuam cada sinal vital por faixas — SpO2, frequência
cardíaca e respiratória, pressão sistólica. Usamos só a ideia (faixas por
variável, com um degrau "alto" e outro "máximo"), com cortes arredondados para
uma UTI adulta; não é a tabela do NEWS2 e não é referência clínica.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LimiarVariavel:
    """Faixa clínica de uma variável. ``None`` = não há corte naquele sentido.

    A comparação é estrita: ``valor < alta_abaixo`` é ALTA, ``valor <
    maxima_abaixo`` é MAXIMA (e o mesmo para cima).
    """

    variavel: str  # nome da coluna no fluxo: fc, fr, spo2, pas
    nome: str  # nome para a descrição do evento
    unidade: str
    alta_abaixo: float | None = None
    maxima_abaixo: float | None = None
    alta_acima: float | None = None
    maxima_acima: float | None = None


LIMIARES_PADRAO: tuple[LimiarVariavel, ...] = (
    # SpO2 < 92% já pede atenção; < 88% é hipoxemia importante.
    LimiarVariavel("spo2", "SpO2", "%", alta_abaixo=92, maxima_abaixo=88),
    # FC: taquicardia > 120 / > 140 bpm; bradicardia < 50 / < 40 bpm.
    LimiarVariavel("fc", "FC", "bpm", alta_abaixo=50, maxima_abaixo=40, alta_acima=120, maxima_acima=140),
    # FR: taquipneia > 24 / > 30 rpm; bradipneia < 10 / < 8 rpm.
    LimiarVariavel("fr", "FR", "rpm", alta_abaixo=10, maxima_abaixo=8, alta_acima=24, maxima_acima=30),
    # PA sistólica (só a sintética; o BIDMC não tem pressão): < 90 ou > 180 mmHg.
    LimiarVariavel("pas", "PA sistólica", "mmHg", alta_abaixo=90, alta_acima=180),
)


@dataclass(frozen=True)
class ConfigSinais:
    limiares: tuple[LimiarVariavel, ...] = LIMIARES_PADRAO

    # Persistência do limiar: amostras seguidas (1 Hz → segundos) fora da
    # faixa antes de disparar. 5 s evita artefato de 1 s (sensor solto, tosse).
    persistencia_limiar: int = 5

    # Desvio do próprio paciente (z-score robusto = (x - mediana) / (1,4826·MAD)).
    variaveis_desvio: tuple[str, ...] = ("fc", "fr", "spo2")
    janela_desvio_s: float = 120.0  # só o passado: 2 min dão a linha de base recente
    minimo_amostras_desvio: int = 60  # com menos de 1 min de histórico o z-score não é confiável
    z_desvio: float = 4.0  # |z| > 4: bem além da variação normal do próprio paciente
    persistencia_desvio: int = 5  # amostras seguidas com |z| acima do corte
    # SpO2 subindo nunca é alarme; nessas variáveis só conta o desvio para baixo.
    desvio_so_para_baixo: tuple[str, ...] = ("spo2",)
    # Piso da escala do z-score, na unidade da variável. Série muito estável
    # (SpO2 parada em 98%) tem MAD = 0 e qualquer 1% viraria z infinito.
    # Com z > 4, o piso exige ao menos 12 bpm de FC, 8 rpm de FR e 4 pontos de
    # SpO2 de afastamento. Ajustado no BIDMC: FC 2→3 e FR 1,5→2 baixaram os
    # eventos sem plantio de 7,34 para 5,79 por hora, sem perder recall.
    escala_minima: dict[str, float] = field(default_factory=lambda: {"fc": 3.0, "fr": 2.0, "spo2": 1.0})

    # Supressor: o mesmo (paciente, tipo) não repete antes de 300 s, e reabre
    # quando a variável fica normal por 30 s seguidos (novo episódio).
    supressao_s: float = 300.0
    normal_para_reabrir_s: float = 30.0

    # Evidência: o CSV guarda 120 s ao redor do evento (60 s antes e 60 s depois).
    meia_janela_evidencia_s: float = 60.0


@dataclass(frozen=True)
class ConfigInjecao:
    """Faixas das anomalias plantadas (RF-45)."""

    duracao_min_s: int = 30
    duracao_max_s: int = 90
    spo2_alvo: tuple[float, float] = (82.0, 86.0)  # queda_spo2: rampa até aqui e volta
    # Paciente que já vive em 85% (BIDMC 32 e 49) não teria queda nenhuma até
    # 82–86; a queda plantada é de pelo menos 6 pontos abaixo da mediana.
    queda_minima_spo2: float = 6.0
    taquicardia_delta: tuple[float, float] = (40.0, 60.0)  # bpm somados à FC
    bradicardia_alvo: tuple[float, float] = (35.0, 45.0)  # bpm
    taquipneia_alvo: tuple[float, float] = (30.0, 35.0)  # rpm
    degrau_fc_delta: tuple[float, float] = (20.0, 25.0)  # bpm, degrau seco
    rampa_s: int = 5  # subida/descida das anomalias que não são degrau nem queda de SpO2
    # No plantio aleatório: começar depois de a janela do desvio ter o mínimo
    # de amostras, e separar anomalias por mais que a tolerância da avaliação.
    margem_inicio_s: int = 90
    intervalo_minimo_s: int = 60


@dataclass(frozen=True)
class ConfigAvaliacao:
    tolerancia_s: float = 30.0  # evento até 30 s depois do fim da anomalia ainda é acerto
    anomalias_por_gravacao: int = 2  # ~8 min por gravação; cabem duas de até 90 s com folga


CONFIG = ConfigSinais()
INJECAO = ConfigInjecao()
AVALIACAO = ConfigAvaliacao()
