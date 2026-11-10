"""Verifica o ambiente. Sai com 0 quando o essencial está pronto e 1 quando falta algo.

Uso: python scripts/check_env.py
"""

from __future__ import annotations

import importlib
import sys

ESSENCIAIS = [
    "numpy", "pandas", "cv2", "ultralytics", "soundfile", "parselmouth", "imageio_ffmpeg",
    "azure.cognitiveservices.speech", "azure.ai.textanalytics", "openai", "streamlit", "dotenv",
]


def main() -> int:
    falhas = 0
    ok = sys.version_info[:2] >= (3, 11)
    print(f"[{'ok' if ok else 'FALHA'}] Python {sys.version.split()[0]} (precisa de 3.11+)")
    falhas += not ok

    for modulo in ESSENCIAIS:
        try:
            importlib.import_module(modulo)
            print(f"[ok] {modulo}")
        except Exception as erro:  # noqa: BLE001
            print(f"[FALHA] {modulo}: {erro}")
            falhas += 1

    try:
        from monitor.config import CAMINHOS, carregar_credenciais, modo_nuvem

        cred = carregar_credenciais()
        modo = modo_nuvem()
        print(f"[ok] modo da nuvem: {modo}")
        for nome, tem in [
            ("Azure Speech", cred.tem_azure_fala),
            ("Azure AI Language", cred.tem_azure_linguagem),
            ("OpenAI", cred.tem_openai),
        ]:
            estado = "real" if tem and modo != "simulado" else "simulado (gravação ou heurística)"
            print(f"[info] {nome}: {estado}")

        for peso in ("yolov8n-pose.pt", "yolov8n.pt"):
            existe = (CAMINHOS.modelos / peso).exists()
            print(f"[{'ok' if existe else 'aviso'}] models/{peso}" + ("" if existe else " — baixa sozinho no primeiro uso"))

        bidmc = CAMINHOS.brutos / "bidmc"
        n = len(list(bidmc.glob("*_Numerics.csv"))) if bidmc.exists() else 0
        print(f"[{'ok' if n else 'aviso'}] BIDMC: {n} gravações" + ("" if n else " — rode python scripts/baixar_bidmc.py"))
    except Exception as erro:  # noqa: BLE001
        print(f"[FALHA] pacote monitor: {erro} — rode pip install -e .")
        falhas += 1

    try:
        import imageio_ffmpeg

        print(f"[ok] ffmpeg: {imageio_ffmpeg.get_ffmpeg_exe()}")
    except Exception as erro:  # noqa: BLE001
        print(f"[FALHA] ffmpeg: {erro}")
        falhas += 1

    print("ambiente pronto" if not falhas else f"{falhas} falha(s)")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
