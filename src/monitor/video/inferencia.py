"""YOLOv8 por quadro: pose (17 pontos COCO) e objetos (leito, cadeira), com cache (RF-02).

Rodar dois modelos em CPU custa caro; o resultado de cada vídeo fica em
``results/cache_video/<hash>.json``. A chave junta o conteúdo do arquivo, a
taxa de amostragem, os pesos e os limiares de confiança: mudou qualquer um,
roda de novo.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from monitor.video.config import ConfigInferencia
from monitor.video.leitura import Metadados, iterar_quadros, ler_metadados
from monitor.video.tipos import Objeto, Pessoa, QuadroAnalisado

VERSAO_CACHE = 1


@dataclass(frozen=True)
class ResultadoInferencia:
    metadados: Metadados
    quadros: list[QuadroAnalisado]
    origem: str  # "modelo" ou "cache"
    s_por_quadro: float  # segundos por quadro analisado (leitura + dois modelos), medido quando rodou o modelo
    caminho_cache: Path


class Analisador:
    """Carrega os dois modelos uma vez e analisa uma imagem por chamada."""

    def __init__(self, cfg: ConfigInferencia = ConfigInferencia()) -> None:
        from ultralytics import YOLO  # importado aqui: os módulos puros não pagam o custo do torch

        self.cfg = cfg
        self.pose = YOLO(str(cfg.modelo_pose))
        self.objetos = YOLO(str(cfg.modelo_objetos))
        nomes = self.objetos.names
        self.classes = [i for i, nome in nomes.items() if nome in cfg.classes_objeto]

    def analisar(self, imagem: np.ndarray, t_s: float) -> QuadroAnalisado:
        r = self.pose(imagem, verbose=False, conf=self.cfg.conf_pessoa_min)[0]
        pessoas: list[Pessoa] = []
        if r.keypoints is not None and len(r.boxes):
            xy = r.keypoints.xy.cpu().numpy().astype(float)
            conf = r.keypoints.conf
            conf = conf.cpu().numpy() if conf is not None else np.ones(xy.shape[:2])
            caixas = r.boxes.xyxy.cpu().numpy()
            confs = r.boxes.conf.cpu().numpy()
            for k in range(len(caixas)):
                pontos = xy[k].copy()
                pontos[conf[k] < self.cfg.conf_ponto_min] = np.nan  # ponto incerto vira NaN (RF-02)
                pessoas.append(Pessoa(pontos, conf[k].astype(float), tuple(float(v) for v in caixas[k]),
                                      float(confs[k])))
        o = self.objetos(imagem, verbose=False, conf=self.cfg.conf_objeto_min, classes=self.classes)[0]
        objetos = [
            Objeto(o.names[int(c)], tuple(float(v) for v in caixa), float(p))
            for caixa, c, p in zip(o.boxes.xyxy.cpu().numpy(), o.boxes.cls.cpu().numpy(), o.boxes.conf.cpu().numpy())
        ]
        return QuadroAnalisado(t_s, pessoas, objetos)


def chave_cache(caminho: Path, cfg: ConfigInferencia) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    h.update(json.dumps([VERSAO_CACHE, cfg.fps_alvo, cfg.modelo_pose.name, cfg.modelo_objetos.name,
                         cfg.conf_pessoa_min, cfg.conf_ponto_min, cfg.conf_objeto_min,
                         list(cfg.classes_objeto)]).encode())
    return h.hexdigest()[:32]


def analisar_video(
    caminho: Path,
    cfg: ConfigInferencia = ConfigInferencia(),
    usar_cache: bool = True,
    analisador: Analisador | None = None,
) -> ResultadoInferencia:
    caminho = Path(caminho)
    arquivo_cache = cfg.dir_cache / f"{chave_cache(caminho, cfg)}.json"
    if usar_cache and arquivo_cache.exists():
        dados: dict[str, Any] = json.loads(arquivo_cache.read_text(encoding="utf-8"))
        return ResultadoInferencia(Metadados(**dados["metadados"]),
                                   [QuadroAnalisado.from_dict(q) for q in dados["quadros"]],
                                   "cache", float(dados["s_por_quadro"]), arquivo_cache)

    metadados = ler_metadados(caminho)
    analisador = analisador or Analisador(cfg)
    inicio = time.perf_counter()
    quadros = [analisador.analisar(imagem, t) for t, imagem in iterar_quadros(caminho, cfg.fps_alvo)]
    s_por_quadro = (time.perf_counter() - inicio) / max(len(quadros), 1)

    arquivo_cache.parent.mkdir(parents=True, exist_ok=True)
    arquivo_cache.write_text(json.dumps({
        "versao": VERSAO_CACHE,
        "video": caminho.name,
        "fps_alvo": cfg.fps_alvo,
        "metadados": asdict(metadados),
        "s_por_quadro": round(s_por_quadro, 4),
        "quadros": [q.to_dict() for q in quadros],
    }, ensure_ascii=False), encoding="utf-8")
    return ResultadoInferencia(metadados, quadros, "modelo", s_por_quadro, arquivo_cache)
