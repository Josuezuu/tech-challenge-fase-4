"""Ponta a ponta com YOLO de verdade: vídeo curto montado de ``bus.jpg`` (pessoas em pé na rua).

Prova que leitura → inferência (com cache) → análise → anotação → relatório roda.
Não avalia acerto: não há queda nem leito na imagem.
"""

from datetime import datetime

import cv2
import pytest

from monitor.config import Credenciais
from monitor.eventos import carregar_eventos
from monitor.nuvem.openai_llm import ClienteLLM
from monitor.video.pipeline import processar
from tests.video import sintetico as s

pytestmark = pytest.mark.lento

SEM_CHAVE = Credenciais(None, None, None, None, None, "gpt-4o-mini")
INICIO = datetime(2026, 11, 12, 14, 3, 30)


@pytest.fixture(scope="module")
def video_bus(tmp_path_factory):
    from ultralytics.utils import ASSETS

    imagem = cv2.imread(str(ASSETS / "bus.jpg"))
    imagem = cv2.resize(imagem, (imagem.shape[1] // 2, imagem.shape[0] // 2))
    return s.gravar_video(tmp_path_factory.mktemp("midia") / "bus.mp4", imagem, segundos=3, fps=10, deslocamento_px=4)


def test_pipeline_quarto_de_ponta_a_ponta_e_cache(video_bus, tmp_path):
    cliente = ClienteLLM(SEM_CHAVE, "auto", tmp_path / "gravadas")
    r = processar(video_bus, "quarto", "teste-bus", INICIO, fps_alvo=5, saida=tmp_path, cliente_llm=cliente)
    quadros = r.inferencia.quadros
    assert r.inferencia.origem == "modelo"
    assert len(quadros) == 15
    assert all(len(q.pessoas) >= 3 for q in quadros)  # bus.jpg tem 4 pessoas
    assert quadros[0].pessoas[0].pontos.shape == (17, 2)
    print(f"\ntempo por quadro (CPU, {r.inferencia.metadados.largura}x{r.inferencia.metadados.altura}): "
          f"{r.inferencia.s_por_quadro:.3f} s")

    cap = cv2.VideoCapture(str(r.video_anotado))
    assert cap.isOpened() and cap.get(cv2.CAP_PROP_FRAME_COUNT) == 15
    cap.release()
    assert (tmp_path / "eventos" / "video_teste-bus.jsonl").exists()
    assert carregar_eventos(tmp_path / "eventos" / "movimentacao_teste-bus.jsonl") == r.eventos_movimentacao
    assert r.relatorio.exists() and r.texto_origem == "simulado"

    de_novo = processar(video_bus, "quarto", "teste-bus", INICIO, fps_alvo=5, saida=tmp_path,
                        anotar=False, cliente_llm=cliente)
    assert de_novo.inferencia.origem == "cache"
    assert de_novo.inferencia.caminho_cache == r.inferencia.caminho_cache
    assert [len(q.pessoas) for q in de_novo.inferencia.quadros] == [len(q.pessoas) for q in quadros]


def test_pipeline_fisioterapia_de_ponta_a_ponta(video_bus, tmp_path):
    cliente = ClienteLLM(SEM_CHAVE, "auto", tmp_path / "gravadas")
    r = processar(video_bus, "fisioterapia", "teste-bus", INICIO, saida=tmp_path, cliente_llm=cliente)
    assert r.fisio is not None and r.fisio.total == 0  # ninguém levanta o braço
    assert "Fisioterapia" in r.relatorio.read_text(encoding="utf-8")
