"""Parâmetros do motor de alertas e da guarda do texto."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConfigAlertas:
    # Duas modalidades diferentes com evento ≥ ALTA dentro de 10 min, olhando
    # para trás a partir do evento novo, viram um alerta CRÍTICO de concordância.
    # 10 min cobre o encadeamento típico (dessaturação → queda, fala de dor →
    # FC alta) sem juntar fatos de outro momento do plantão.
    janela_concordancia_s: float = 600.0
    # Mesmo (paciente, tipo, nível) fora da concordância: no máximo um alerta a
    # cada 5 min, para o mesmo fato não inundar a equipe.
    intervalo_minimo_s: float = 300.0

    # Guarda do texto redigido pela LLM: acima disso, ou com termo proibido,
    # usa o modelo fixo. 600 caracteres ≈ 3 frases longas.
    max_caracteres: int = 600
    # Termos que indicam diagnóstico ou conduta (comparação sem acento e em
    # minúsculas). O alerta descreve o que foi observado; quem decide é a equipe.
    termos_proibidos: tuple[str, ...] = (
        "diagnostico", "diagnosticado", "diagnosticada", "diagnosticar",
        "prescrever", "prescreva", "prescrevo", "administre", "administrar",
        "tem pneumonia", "esta com pneumonia", "sofreu um infarto", "esta infartando",
        "recomendo", "deve tomar", "aplicar medicacao", "aumente a dose", "suspenda",
    )
    frase_final: str = "Avaliação da equipe necessária."
    max_eventos_no_texto: int = 4  # o modelo fixo cita até 4 eventos e resume o resto


CONFIG = ConfigAlertas()
