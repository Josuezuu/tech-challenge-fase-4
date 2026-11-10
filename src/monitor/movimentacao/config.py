"""Parâmetros da movimentação: série por janela, desvio do padrão, saída do leito e imobilidade."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConfigMovimentacao:
    janela_s: float = 10.0  # cada linha da série resume 10 s de vídeo
    z_limiar: float = 4.0  # z-score robusto acima disso = agitação (4 MADs: raro em série calma)
    min_janelas: int = 6  # só compara depois de 1 min de histórico (6 janelas de 10 s)
    mad_minimo: float = 0.01  # corpos/s: piso do MAD, senão série perfeitamente parada dá z infinito
    presenca_min: float = 0.5  # janela com paciente em menos da metade do tempo não entra no z-score
    saida_dentro_s: float = 3.0  # quadril no leito por 3 s confirma "estava no leito"
    saida_fora_s: float = 3.0  # e fora por 3 s confirma a saída (ignora troca de posição na borda)
    # Imobilidade: 60 s só para caber na demonstração gravada. Na prática clínica
    # (prevenção de lesão por pressão) o alvo é mudança de decúbito a cada 2 h,
    # ou seja, imobilidade_s = 7200.
    imobilidade_s: float = 60.0
    imobilidade_limiar: float = 0.05  # corpos/s: abaixo disso o paciente está parado (tremor do esqueleto ~0,02)
    mediana_quadros: int = 5  # mediana móvel da velocidade (1 s a 5 fps) contra tremor do esqueleto
