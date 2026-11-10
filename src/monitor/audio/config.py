"""Parâmetros da análise de áudio (termos críticos e alteração vocal).

Cada valor tem unidade e motivo. Os detectores recebem um ``ConfigAudio``;
o padrão é ``CONFIG``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from monitor.eventos import Severidade

# Termos curados (sem acento, minúsculos) e a severidade de cada um.
# ALTA: sintoma que pede avaliação imediata (cardiorrespiratório, perda de consciência).
# INFO: sintoma inespecífico, útil quando concorda com outra fonte.
TERMOS_CRITICOS: dict[str, Severidade] = {
    "dor no peito": Severidade.ALTA,
    "falta de ar": Severidade.ALTA,
    "dificuldade para respirar": Severidade.ALTA,
    "desmaio": Severidade.ALTA,
    "tontura": Severidade.INFO,
    "cansaco": Severidade.INFO,
    "fadiga": Severidade.INFO,
    "palpitacao": Severidade.INFO,
    "febre": Severidade.INFO,
}

# Atributos acústicos, na ordem em que aparecem no relatório.
ATRIBUTOS: tuple[str, ...] = (
    "taxa_fala_ppm",
    "proporcao_pausa",
    "pausas_por_min",
    "f0_media_hz",
    "f0_dp_hz",
    "energia_db",
    "jitter_local",
    "shimmer_local",
    "hnr_db",
)

# Direção de piora: +1 = piora quando sobe, -1 = piora quando desce,
# 0 = só informativo (a F0 média muda com o humor e a frase, não indica piora).
DIRECAO_PIORA: dict[str, int] = {
    "taxa_fala_ppm": -1,
    "proporcao_pausa": +1,
    "pausas_por_min": +1,
    "f0_media_hz": 0,
    "f0_dp_hz": -1,  # voz monótona
    "energia_db": -1,  # voz fraca
    "jitter_local": +1,
    "shimmer_local": +1,
    "hnr_db": -1,  # voz soprosa/rouca
}

# Desvio mínimo por atributo, usado no denominador do z quando a referência
# é curta (poucas janelas dão desvio quase zero e o z explode). Ordem de
# grandeza da variação da mesma pessoa lendo o mesmo texto em dias diferentes.
DESVIO_MINIMO: dict[str, float] = {
    "taxa_fala_ppm": 10.0,  # palavras por minuto
    "proporcao_pausa": 0.03,  # fração da janela
    "pausas_por_min": 2.0,  # pausas por minuto
    "f0_media_hz": 5.0,  # Hz
    "f0_dp_hz": 2.0,  # Hz
    "energia_db": 1.5,  # dB
    "jitter_local": 0.002,  # fração (0,2 ponto percentual)
    "shimmer_local": 0.01,  # fração (1 ponto percentual)
    "hnr_db": 1.0,  # dB
}


@dataclass(frozen=True)
class ConfigAudio:
    # --- Conversão
    taxa_amostragem_hz: int = 16_000  # o Azure Speech espera 16 kHz mono PCM 16 bits

    # --- Termos críticos e sentimento
    termos_criticos: dict[str, Severidade] = field(default_factory=lambda: dict(TERMOS_CRITICOS))
    categorias_termo: tuple[str, ...] = ("SymptomOrSign", "Diagnosis")
    limiar_sentimento_negativo: float = 0.8  # confiança do rótulo "negative" (0–1)

    # --- Janelas e VAD por energia
    janela_s: float = 5.0  # uma janela de 5 s tem ~12 palavras: taxa já é estável
    janela_minima_s: float = 2.5  # janela final mais curta que isso é descartada
    fala_minima_s: float = 1.0  # janela com menos fala que isso não entra na média
    quadro_s: float = 0.025  # quadro do VAD (25 ms, padrão em fala)
    percentil_ruido: float = 20.0  # o percentil 20 da energia estima o ruído de fundo
    margem_vad_db: float = 10.0  # silêncio = energia < ruído + 10 dB
    pausa_minima_s: float = 0.25  # silêncio menor é articulação, não pausa
    piso_energia: float = 1e-10  # soma no quadrado médio para log de silêncio digital (−100 dB)

    # --- Praat (parselmouth)
    f0_min_hz: float = 75.0  # faixa de F0 de voz adulta
    f0_max_hz: float = 500.0
    jitter_periodo_min_s: float = 0.0001  # parâmetros padrão do Praat para jitter/shimmer
    jitter_periodo_max_s: float = 0.02
    jitter_fator_max: float = 1.3
    shimmer_fator_amplitude_max: float = 1.6

    # --- Comparação com a referência
    limiar_z: float = 2.0  # |z| ≥ 2: fora de ~95% da variação da referência
    min_atributos_alterados: int = 2  # um atributo sozinho é ruído; dois é padrão
    desvio_minimo: dict[str, float] = field(default_factory=lambda: dict(DESVIO_MINIMO))
    direcao_piora: dict[str, int] = field(default_factory=lambda: dict(DIRECAO_PIORA))


CONFIG = ConfigAudio()
