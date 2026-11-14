"""Parâmetros do vídeo: inferência, escolha do paciente, fisioterapia e quarto.

Todo número usado pelos detectores mora aqui, com unidade e motivo. Os
valores padrão são os da spec (``specs/features/video/spec.md``) e serão
recalibrados com as gravações do grupo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from monitor.config import CAMINHOS

# Índices dos 17 pontos COCO usados pelo YOLOv8-pose.
NARIZ = 0
OMBRO_E, OMBRO_D = 5, 6
COTOVELO_E, COTOVELO_D = 7, 8
PUNHO_E, PUNHO_D = 9, 10
QUADRIL_E, QUADRIL_D = 11, 12
JOELHO_E, JOELHO_D = 13, 14
TORNOZELO_E, TORNOZELO_D = 15, 16


@dataclass(frozen=True)
class ConfigInferencia:
    fps_alvo: float = 5.0  # quadros/s analisados; 5 basta para queda (~1 s) e custa 1/6 de 30 fps
    modelo_pose: Path = field(default=CAMINHOS.modelos / "yolov8n-pose.pt")
    modelo_objetos: Path = field(default=CAMINHOS.modelos / "yolov8n.pt")
    conf_pessoa_min: float = 0.4  # caixa de pessoa abaixo disso é descartada (ruído)
    conf_ponto_min: float = 0.3  # ponto do esqueleto abaixo disso vira NaN (spec RF-02)
    conf_objeto_min: float = 0.25  # leito visto de cima tem confiança baixa; 0.25 ainda é estável
    classes_objeto: tuple[str, ...] = ("bed", "chair")  # nomes COCO de interesse
    dir_cache: Path = field(default=CAMINHOS.resultados / "cache_video")


@dataclass(frozen=True)
class ConfigPaciente:
    salto_max_corpos: float = 1.0  # deslocamento máximo entre quadros, em tamanhos de corpo, para ser a mesma pessoa
    perda_max_s: float = 3.0  # sem achar o paciente por mais que isso, escolhe de novo pela regra inicial


@dataclass(frozen=True)
class Exercicio:
    """Ângulo medido em três pontos (a, vértice, c) de cada lado do corpo.

    ``crescente``: a repetição aumenta o ângulo (elevação lateral) ou diminui
    (agachamento). ``amplitude_esperada`` é o pico que conta como completa.
    """

    nome: str
    pontos_esquerda: tuple[int, int, int]
    pontos_direita: tuple[int, int, int]
    crescente: bool
    limiar_inicio: float  # graus: passou disso, começou a repetição
    amplitude_esperada: float  # graus
    histerese: float = 5.0  # graus: a repetição só termina a 5° aquém do limiar (evita contar tremor)


EXERCICIOS: dict[str, Exercicio] = {
    # Quadril–ombro–cotovelo: braço junto ao corpo ~10°, na horizontal ~90°.
    "elevacao_lateral": Exercicio(
        nome="elevação lateral",
        pontos_esquerda=(QUADRIL_E, OMBRO_E, COTOVELO_E),
        pontos_direita=(QUADRIL_D, OMBRO_D, COTOVELO_D),
        crescente=True,
        limiar_inicio=30.0,
        amplitude_esperada=80.0,
    ),
    # Quadril–joelho–tornozelo: em pé ~175°; agachamento útil chega a 100° ou menos.
    "agachamento": Exercicio(
        nome="agachamento",
        pontos_esquerda=(QUADRIL_E, JOELHO_E, TORNOZELO_E),
        pontos_direita=(QUADRIL_D, JOELHO_D, TORNOZELO_D),
        crescente=False,
        limiar_inicio=150.0,
        amplitude_esperada=100.0,
    ),
}


@dataclass(frozen=True)
class ConfigFisioterapia:
    exercicio: str = "elevacao_lateral"
    suavizacao_quadros: int = 3  # mediana móvel do ângulo (3 quadros = 0,6 s a 5 fps) contra tremor do esqueleto


@dataclass(frozen=True)
class ConfigQuarto:
    zona_s: float = 10.0  # o leito é estimado pela mediana das caixas `bed` nos primeiros 10 s
    # ...desde que `bed` apareça em pelo menos metade desses quadros. Leito de verdade é móvel e aparece
    # sempre (76/76 e 70/70 quadros nas gravações de 14/11); o YOLOv8n às vezes chama de `bed` a pessoa
    # deitada no chão (7/112 e 1/122), e a zona nascia embaixo de quem caiu.
    zona_presenca_min: float = 0.5
    ampliacao_leito: float = 0.10  # caixa do leito ampliada 10% (quadril de quem senta na borda fica dentro)
    poligono_leito: tuple[tuple[float, float], ...] | None = None  # px; usado quando o modelo não acha o leito
    queda_inclinacao_graus: float = 60.0  # tronco a mais de 60° da vertical = deitado/caído
    # Quadril desce mais que 0,3 tamanho do corpo... Recalibrado (era 0,4) com as gravações do grupo de
    # 14/11, câmera de lado na altura do peito: queda real 0,39, deitar devagar no chão 0,20. Com câmera
    # lateral, 0,4 fica perto do máximo físico (quadril em pé ~metade da altura; no chão, rente ao piso).
    # O tropeço desce 0,40 e quem o barra é a permanência abaixo, não a descida.
    queda_descida_corpos: float = 0.3
    queda_janela_s: float = 1.5  # ...em até 1,5 s (deitar devagar leva mais)
    # Levantou = quadril voltou a menos de 0,15 corpo da altura de antes da queda (metade da descida que
    # caracteriza a queda). Sentar no chão não é levantar: o tronco fica abaixo de 60°, mas o quadril segue
    # rente ao piso (gravação de 14/11: sentado, 0,27 corpo abaixo; de pé de novo, ~0).
    queda_recuperacao_corpos: float = 0.15
    queda_permanencia_s: float = 2.0  # e fica baixo/horizontal por 2 s (descarta tropeço com recuperação)
    queda_refratario_s: float = 10.0  # uma queda gera um evento, não um por quadro
    ausencia_s: float = 10.0  # ninguém no quadro por 10 s = paciente ausente
