from datetime import datetime

import numpy as np
import pytest

from monitor.video.config import EXERCICIOS, ConfigFisioterapia
from monitor.video.fisioterapia import analisar_fisioterapia, angulo_exercicio, contar_repeticoes
from tests.video.sintetico import EM_PE_FORA, Postura, pose, serie_elevacao

INICIO = datetime(2026, 11, 12, 14, 0, 0)


def test_pose_sintetica_tem_o_angulo_do_braco_pedido():
    for graus in (10, 45, 90, 120):
        p = pose(Postura(EM_PE_FORA.x, EM_PE_FORA.y, braco=graus))
        assert angulo_exercicio(p, EXERCICIOS["elevacao_lateral"]) == pytest.approx(graus, abs=0.01)


def test_dez_repeticoes_com_tres_incompletas_geram_tres_eventos():
    picos = [95, 90, 55, 92, 88, 55, 100, 91, 55, 94]
    quadros = serie_elevacao(picos)
    r = analisar_fisioterapia([q.pessoas[0] for q in quadros], [q.t_s for q in quadros], "fisio-1", INICIO)
    assert r.total == 10
    assert r.incompletas == 3
    assert [e.tipo for e in r.eventos] == ["amplitude_insuficiente"] * 3
    assert all(e.valor == pytest.approx(55, abs=2) for e in r.eventos)
    assert "Repetição 3 de elevação lateral" in r.eventos[0].descricao
    assert r.amplitude_media == pytest.approx(np.mean(picos), abs=2)


def test_esqueleto_que_some_no_meio_nao_quebra_a_repeticao():
    quadros = serie_elevacao([90, 90])
    pessoas = [None if 5 <= i <= 6 else q.pessoas[0] for i, q in enumerate(quadros)]
    r = analisar_fisioterapia(pessoas, [q.t_s for q in quadros], "fisio-1", INICIO)
    assert r.total == 2 and r.incompletas == 0


def test_lado_mais_visivel_e_o_de_maior_confianca():
    p = pose(Postura(EM_PE_FORA.x, EM_PE_FORA.y, braco=70))
    p.pontos[8] = p.pontos[6] + [0, 50]  # cotovelo direito colado ao corpo
    p.confiancas[[12, 6, 8]] = 0.35
    assert angulo_exercicio(p, EXERCICIOS["elevacao_lateral"]) == pytest.approx(70, abs=0.01)


def test_agachamento_usa_o_menor_angulo_do_joelho():
    t = np.arange(0, 12, 0.2)
    # Três descidas: até 90° (completa), 120° (incompleta), 95° (completa).
    minimos = [90, 120, 95]
    angulos = np.full(len(t), 175.0)
    for k, m in enumerate(minimos):
        trecho = (t >= 4 * k) & (t < 4 * k + 3)
        fase = (t[trecho] - 4 * k) / 3
        angulos[trecho] = 175 - (175 - m) * np.sin(np.pi * fase)
    reps = contar_repeticoes(t, angulos, EXERCICIOS["agachamento"])
    assert [r.completa for r in reps] == [True, False, True]
    assert reps[1].pico == pytest.approx(120, abs=1)


def test_configuracao_padrao_e_elevacao_lateral():
    assert ConfigFisioterapia().exercicio == "elevacao_lateral"
