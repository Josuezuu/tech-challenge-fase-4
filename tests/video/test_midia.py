"""Leitura, anotação, relatório e avaliação sem modelo (vídeos sintéticos pequenos)."""

from dataclasses import replace
from datetime import datetime

import cv2
import numpy as np
import pytest

from monitor.config import Credenciais
from monitor.nuvem.gravacao import Gravador
from monitor.nuvem.openai_llm import ClienteLLM
from monitor.video.anotacao import gravar_anotado
from monitor.video.avaliacao import avaliar
from monitor.video.leitura import iterar_quadros, ler_metadados
from monitor.video.paciente import escolher_paciente
from monitor.video.quarto import calcular_estados, detectar_quedas, estimar_zona
from monitor.video.relatorio import dados_da_sessao, escrever_relatorio, texto_modelo_fixo
from tests.video import sintetico as s

INICIO = datetime(2026, 11, 12, 14, 3, 30)
SEM_CHAVE = Credenciais(None, None, None, None, None, "gpt-4o-mini")


def test_leitura_amostra_10_s_de_30_fps_em_50_quadros(tmp_path):
    video = s.gravar_video(tmp_path / "v.mp4", np.zeros((48, 64, 3), np.uint8), segundos=10, fps=30)
    meta = ler_metadados(video)
    assert meta.fps == pytest.approx(30) and meta.total_quadros == 300 and meta.duracao_s == pytest.approx(10)
    t = [t for t, _ in iterar_quadros(video, fps_alvo=5)]
    assert len(t) == 50
    assert t[0] == 0 and all(b > a for a, b in zip(t, t[1:]))
    assert t[1] == pytest.approx(0.2, abs=0.02)


def test_video_anotado_tem_a_duracao_amostrada_e_recorte_da_queda(tmp_path):
    quadros = s.cena_queda()
    video = s.gravar_video(tmp_path / "queda.mp4", np.zeros((480, 640, 3), np.uint8), segundos=len(quadros) / 5, fps=5)
    zona = estimar_zona(quadros)
    pacientes = escolher_paciente(quadros, zona)
    estados = calcular_estados(quadros, pacientes, zona)
    quedas = detectar_quedas(estados, "leito-12", INICIO)
    marcas = [((e.instante - INICIO).total_seconds(), e.tipo) for e in quedas]
    destino = tmp_path / "saida" / "queda_anotado.mp4"
    recortes = gravar_anotado(video, 5, quadros, pacientes, zona, ["teste"] * len(quadros), marcas,
                              destino, tmp_path / "saida" / "recortes")
    cap = cv2.VideoCapture(str(destino))
    assert cap.get(cv2.CAP_PROP_FRAME_COUNT) == len(quadros)
    assert cap.get(cv2.CAP_PROP_FPS) == pytest.approx(5)
    cap.release()
    assert len(recortes) == 1 and recortes[0].name.startswith("00_queda_")
    imagem = cv2.imread(str(recortes[0]))
    assert imagem is not None and imagem.sum() > 0  # o esqueleto e o aviso foram desenhados


def test_relatorio_sem_chave_usa_o_modelo_fixo_e_linka_o_recorte(tmp_path):
    quedas = detectar_quedas(calcular_estados(*_cena_queda_com_zona()), "leito-12", INICIO)
    recorte = tmp_path / "evidencias" / "x.jpg"
    eventos = [replace(quedas[0], evidencia={"recorte": str(recorte)})]
    dados = dados_da_sessao("V5", "quarto", "leito-12", INICIO, 15.6, eventos)
    cliente = ClienteLLM(SEM_CHAVE, "auto", tmp_path / "gravadas")
    destino = tmp_path / "relatorios" / "V5.md"
    redacao = escrever_relatorio(destino, dados, eventos, cliente)
    texto = destino.read_text(encoding="utf-8")
    assert redacao.origem == "simulado"
    assert redacao.texto == texto_modelo_fixo(dados)
    assert "Evento mais grave: queda às 14:03:35" in texto
    assert "](../evidencias/x.jpg)" in texto
    assert "| 14:03:35 | queda | MAXIMA |" in texto


def test_modelo_fixo_da_fisioterapia_e_sem_eventos():
    dados = dados_da_sessao("V1", "fisioterapia", "fisio-1", INICIO, 120, [])
    dados["fisioterapia"] = {"exercicio": "elevacao_lateral", "repeticoes": 10, "incompletas": 3,
                             "amplitude_media_graus": 78.4}
    texto = texto_modelo_fixo(dados)
    assert "10 repetições, 3 com amplitude insuficiente, amplitude média de 78°" in texto
    assert "Nenhum evento registrado" in texto


def test_avaliacao_conta_acerto_com_tolerancia_falso_positivo_e_pula_clipe_sem_anotacao():
    anotacoes = {
        "V5.mp4": {"cenario": "quarto", "eventos": [{"tipo": "queda", "t_s": 12.0},
                                                    {"tipo": "saida_do_leito", "t_s": 40.0}]},
        "V3.mp4": {"cenario": "quarto", "eventos": []},
    }
    detectados = {
        "V5.mp4": [("queda", 13.5), ("saida_do_leito", 45.0), ("paciente_ausente", 60.0)],
        "V3.mp4": [],
        "extra.mp4": [("queda", 1.0)],
    }
    r = avaliar(anotacoes, detectados)
    assert r["clipes"]["V5.mp4"]["acertos"] == 1
    assert r["clipes"]["V5.mp4"]["falsos_positivos"] == 2  # saída fora da tolerância + ausência não anotada
    assert r["clipes"]["V5.mp4"]["perdidos"] == [{"tipo": "saida_do_leito", "t_s": 40.0}]
    assert r["por_tipo"]["queda"] == {"esperados": 1, "acertos": 1, "falsos_positivos": 0,
                                      "sensibilidade": 1.0, "precisao": 1.0}
    assert r["total"]["sensibilidade"] == 0.5
    assert r["pulados"] == ["extra.mp4"]


def _cena_queda_com_zona():
    quadros = s.cena_queda()
    zona = estimar_zona(quadros)
    return quadros, escolher_paciente(quadros, zona), zona
