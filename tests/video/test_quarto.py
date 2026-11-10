from datetime import datetime

import numpy as np
import pytest

from monitor.video.config import ConfigQuarto
from monitor.video.paciente import escolher_paciente
from monitor.video.quarto import calcular_estados, detectar_ausencia, detectar_quedas, estimar_zona
from monitor.video.tipos import QuadroAnalisado
from tests.video import sintetico as s

INICIO = datetime(2026, 11, 12, 14, 3, 30)


def _estados(quadros: list[QuadroAnalisado], cfg: ConfigQuarto = ConfigQuarto()):
    zona = estimar_zona(quadros, cfg)
    return calcular_estados(quadros, escolher_paciente(quadros, zona), zona)


def _quedas(quadros: list[QuadroAnalisado]):
    return detectar_quedas(_estados(quadros), "leito-12", INICIO)


def test_zona_e_a_mediana_do_leito_ampliada_ou_o_poligono_do_config():
    quadros = s.cena([(2, s.NA_CAMA, None)])
    x1, y1, x2, y2 = 300, 250, 600, 400
    assert np.allclose(estimar_zona(quadros), ((285, 242.5), (615, 242.5), (615, 407.5), (285, 407.5)))
    sem_leito = s.cena([(2, s.NA_CAMA, None)], leito=None)
    poligono = ((x1, y1), (x2, y1), (x2, y2), (x1, y2))
    assert estimar_zona(sem_leito) is None
    assert estimar_zona(sem_leito, ConfigQuarto(poligono_leito=poligono)) == poligono


def test_estado_no_leito_e_inclinacao_de_quem_esta_deitado():
    e = _estados(s.cena([(1, s.NA_CAMA, None)]))[0]
    assert e.presente and e.no_leito
    assert e.inclinacao == pytest.approx(90)


def test_queda_fora_do_leito_gera_um_evento_maximo():
    eventos = _quedas(s.cena_queda())
    assert [e.tipo for e in eventos] == ["queda"]
    queda = eventos[0]
    assert queda.severidade.name == "MAXIMA" and queda.fonte.value == "video"
    assert 5.0 <= (queda.instante - INICIO).total_seconds() <= 5.8
    assert queda.valor > 0.4


def test_deitar_devagar_na_cama_nao_e_queda():
    assert _quedas(s.cena_deitar_devagar_na_cama()) == []


def test_mesmo_movimento_da_queda_sobre_o_leito_nao_e_queda():
    assert _quedas(s.cena_despencar_no_leito_baixo()) == []
    assert len(_quedas(s.cena_queda(leito=None))) == 1  # sem leito na cena, o mesmo movimento é queda


def test_deitar_devagar_no_chao_nao_e_queda_porque_a_descida_e_lenta():
    assert _quedas(s.cena_deitar_devagar_no_chao()) == []


def test_queda_com_recuperacao_imediata_nao_conta():
    no_chao = s.Postura(230, s.QUADRIL_NO_CHAO, 90)
    quadros = s.cena([(5, s.EM_PE_FORA, None), (0.6, s.EM_PE_FORA, no_chao),
                      (0.6, no_chao, s.EM_PE_FORA), (5, s.EM_PE_FORA, None)])
    assert _quedas(quadros) == []


def test_queda_no_fim_do_video_sem_tempo_de_confirmar_nao_conta():
    no_chao = s.Postura(230, s.QUADRIL_NO_CHAO, 90)
    quadros = s.cena([(5, s.EM_PE_FORA, None), (0.6, s.EM_PE_FORA, no_chao), (1, no_chao, None)])
    assert _quedas(quadros) == []


def test_permanencia_que_termina_entre_dois_quadros_confirma_no_quadro_seguinte():
    no_chao = s.Postura(230, s.QUADRIL_NO_CHAO, 90)
    quadros = s.cena([(5, s.EM_PE_FORA, None), (0.6, s.EM_PE_FORA, no_chao), (2.4, no_chao, None)])
    cfg = ConfigQuarto(queda_permanencia_s=1.5)  # a 5 fps, t + 1,5 s cai entre dois quadros
    zona = estimar_zona(quadros, cfg)
    estados = calcular_estados(quadros, escolher_paciente(quadros, zona), zona)
    assert len(detectar_quedas(estados, "leito-12", INICIO, cfg)) == 1


def test_quadro_sem_quadril_nem_ombros_depois_da_queda_nao_impede_a_confirmacao():
    quadros = s.cena_queda()
    for q in quadros[-30:]:  # últimos 6 s: o YOLO ainda vê a pessoa, mas sem confiança no tronco
        q.pessoas[0].pontos[[5, 6, 11, 12]] = np.nan
    assert len(_quedas(quadros)) == 1


def test_ausencia_de_15_s_gera_um_evento_com_a_duracao():
    eventos = detectar_ausencia(_estados(s.cena_saida_do_quadro()), "leito-12", INICIO)
    assert [e.tipo for e in eventos] == ["paciente_ausente"]
    assert eventos[0].valor == pytest.approx(15)
    assert (eventos[0].instante - INICIO).total_seconds() == pytest.approx(5)


def test_paciente_e_quem_esta_no_leito_e_o_rastreamento_segue_ele():
    enfermeira = s.pose(s.Postura(100, s.QUADRIL_EM_PE), altura=380)  # maior caixa, longe do leito
    quadros = s.cena([(3, s.NA_CAMA, s.Postura(500, s.QUADRIL_NA_CAMA, 90))], extras=[enfermeira])
    escolhidos = escolher_paciente(quadros, estimar_zona(quadros))
    assert all(p is not None and p.caixa[0] > 250 for p in escolhidos)


def test_sem_leito_o_paciente_e_a_maior_caixa_e_quem_salta_longe_nao_e_ele():
    grande = s.pose(s.Postura(150, s.QUADRIL_EM_PE), altura=320)
    pequena = s.pose(s.Postura(500, s.QUADRIL_EM_PE), altura=200)
    quadros = [QuadroAnalisado(0.0, [pequena, grande], []), QuadroAnalisado(0.2, [pequena], [])]
    escolhidos = escolher_paciente(quadros, None)
    assert escolhidos[0] is grande
    assert escolhidos[1] is None  # a outra pessoa está a mais de um corpo de distância
    assert np.isnan(calcular_estados(quadros, escolhidos, None)[1].movimento)
