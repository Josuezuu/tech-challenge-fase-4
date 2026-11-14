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


def test_leito_visto_so_em_poucos_quadros_nao_vira_zona_e_a_queda_continua_sendo_queda():
    # Gravação V5 de 14/11: sem cama na cena, o YOLOv8n chamou de `bed` a pessoa caída no chão
    # em 7 de 112 quadros; a zona nascia embaixo dela e a queda virava "deitou no leito".
    quadros = s.cena_queda(leito=None)
    caida = (150.0, 400.0, 330.0, 470.0)  # caixa em volta de quem está no chão
    for q in quadros:
        if q.t_s >= 6.8 and round(q.t_s * 5) % 4 == 0:  # 1 quadro em 4 depois da queda
            q.objetos.append(s.Objeto("bed", caida, 0.4))
    assert estimar_zona(quadros) is None
    assert len(_quedas(quadros)) == 1


def test_leito_visto_na_maior_parte_dos_quadros_vira_zona():
    quadros = s.cena([(10, s.NA_CAMA, None)])
    for q in quadros[::3]:  # o modelo perde o leito em 1 quadro de cada 3
        q.objetos.clear()
    assert estimar_zona(quadros) is not None


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
    assert queda.valor > ConfigQuarto().queda_descida_corpos


def test_deitar_devagar_na_cama_nao_e_queda():
    assert _quedas(s.cena_deitar_devagar_na_cama()) == []


def test_mesmo_movimento_da_queda_sobre_o_leito_nao_e_queda():
    assert _quedas(s.cena_despencar_no_leito_baixo()) == []
    assert len(_quedas(s.cena_queda(leito=None))) == 1  # sem leito na cena, o mesmo movimento é queda


def test_queda_da_cama_com_o_chao_dentro_da_zona_e_queda():
    # Câmera na altura da cama (gravação de 14/11): o chão logo à frente do leito cai dentro do
    # retângulo da zona. A descida parte de dentro da zona, então é queda *da* cama.
    chao_na_frente = s.Postura(450, 405, 90)  # dentro da zona ampliada (y até 407,5)
    quadros = s.cena([(5, s.NA_CAMA, None), (0.6, s.NA_CAMA, chao_na_frente), (10, chao_na_frente, None)])
    eventos = _quedas(quadros)
    assert [(e.tipo, e.severidade.name) for e in eventos] == [("queda", "MAXIMA")]
    assert "saindo do leito" in eventos[0].descricao


def test_deitar_devagar_no_chao_nao_e_queda_porque_a_descida_e_lenta():
    assert _quedas(s.cena_deitar_devagar_no_chao()) == []


def test_queda_com_recuperacao_gera_um_evento_alto_e_nao_critico():
    no_chao = s.Postura(230, s.QUADRIL_NO_CHAO, 90)
    quadros = s.cena([(5, s.EM_PE_FORA, None), (0.6, s.EM_PE_FORA, no_chao),
                      (0.6, no_chao, s.EM_PE_FORA), (5, s.EM_PE_FORA, None)])
    eventos = _quedas(quadros)
    assert [(e.tipo, e.severidade.name) for e in eventos] == [("queda_com_recuperacao", "ALTA")]
    assert 5.0 <= (eventos[0].instante - INICIO).total_seconds() <= 5.8
    assert "voltado à altura de antes" in eventos[0].descricao


def test_cair_e_ficar_sentado_no_chao_e_queda_grave_e_nao_recuperacao():
    # Gravação de 14/11: sentado no chão, tronco abaixo de 60° e quadril 0,27 corpo abaixo de antes.
    deitado = s.Postura(230, s.QUADRIL_NO_CHAO, 90)
    sentado = s.Postura(230, s.QUADRIL_EM_PE + 0.25 * s.ALTURA, 10)  # entre 0,15 e 0,3 corpo abaixo de antes
    quadros = s.cena([(5, s.EM_PE_FORA, None), (0.6, s.EM_PE_FORA, deitado), (0.6, deitado, sentado),
                      (10, sentado, None)])
    assert [(e.tipo, e.severidade.name) for e in _quedas(quadros)] == [("queda", "MAXIMA")]


def test_queda_que_fica_no_chao_nao_vira_recuperacao_por_um_quadro_ruidoso():
    no_chao = s.Postura(230, s.QUADRIL_NO_CHAO, 90)
    quadros = s.cena([(5, s.EM_PE_FORA, None), (0.6, s.EM_PE_FORA, no_chao), (10, no_chao, None)])
    meio_erguido = s.pose(s.Postura(230, s.QUADRIL_EM_PE, 0))  # o YOLO erra a pose em um quadro
    k = next(i for i, q in enumerate(quadros) if q.t_s >= 6.4)
    quadros[k] = s.QuadroAnalisado(quadros[k].t_s, [meio_erguido], quadros[k].objetos)
    eventos = _quedas(quadros)
    assert [e.tipo for e in eventos] == ["queda"]


def test_deitar_devagar_no_chao_e_levantar_nao_e_queda_nem_com_recuperacao():
    no_chao = s.Postura(150, s.QUADRIL_NO_CHAO, 90)
    quadros = s.cena([(4, s.EM_PE_FORA, None), (5, s.EM_PE_FORA, no_chao), (1, no_chao, None),
                      (3, no_chao, s.EM_PE_FORA), (5, s.EM_PE_FORA, None)])
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
