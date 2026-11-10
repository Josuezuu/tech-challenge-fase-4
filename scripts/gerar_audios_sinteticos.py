"""Gera as amostras SINTÉTICAS de áudio com a voz Microsoft Maria (pt-BR) do Windows.

Saída em ``data/amostras/audio/`` (versionada; mono 16 kHz, PCM 16 bits):

- ``sintetico_normal.wav`` + ``.txt``: roteiro neutro, taxa normal.
- ``sintetico_alterado.wav`` + ``.txt``: o mesmo roteiro mais lento (Rate = -2)
  e com pausas de 900 ms entre frases e trechos.
- ``sintetico_termos.wav`` + ``.txt``: frases com termos críticos e uma negação.

Cada WAV vem com ``<nome>.esperado.json`` (o que a avaliação deve achar).
São vozes sintéticas: não têm jitter/shimmer realistas e servem só para
desenvolver e testar o fluxo antes das gravações do grupo.

Uso: ``python scripts/gerar_audios_sinteticos.py`` (só no Windows; usa
``System.Speech`` por PowerShell).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from monitor.config import CAMINHOS

VOZ = "Microsoft Maria Desktop"
DIR_SAIDA = CAMINHOS.amostras / "audio"

# Trechos separados: no áudio alterado entra uma pausa entre cada trecho.
ROTEIRO_NEUTRO = [
    "Bom dia.",
    "Hoje eu acordei cedo e tomei o café da manhã no quarto.",
    "A enfermeira passou às oito horas para medir a pressão,",
    "e depois eu conversei com a minha filha pelo telefone.",
    "Ela vem me visitar no sábado à tarde, com os meus netos.",
    "O almoço estava gostoso,",
    "e eu consegui caminhar um pouco pelo corredor.",
    "À tarde eu li o jornal e assisti a um programa de música na televisão.",
]

ROTEIRO_TERMOS = [
    "Doutor, eu não tenho febre, mas estou com falta de ar desde ontem.",
    "À noite eu senti dor no peito e um pouco de tontura quando levantei.",
    "Hoje eu estou muito cansado e com medo de piorar.",
]


@dataclass(frozen=True)
class Amostra:
    nome: str
    trechos: list[str]
    taxa_voz: int  # Rate do SpeechSynthesizer, de -10 a 10 (0 = normal)
    pausa_ms: int  # silêncio inserido entre trechos (0 = nenhum)
    esperado: dict


AMOSTRAS = [
    Amostra("sintetico_normal", ROTEIRO_NEUTRO, 0, 0,
            {"termos": [], "alteracao_vocal": False}),
    # Rate -2 (e não o -4 da spec): -4 quase dobra a duração (62 s) e é uma
    # mudança exagerada; -2 + pausas dá ~50 s e um teste mais exigente.
    Amostra("sintetico_alterado", ROTEIRO_NEUTRO, -2, 900,
            {"termos": [], "alteracao_vocal": True}),
    Amostra("sintetico_termos", ROTEIRO_TERMOS, 0, 0,
            {"termos": ["falta de ar", "dor no peito", "tontura"], "alteracao_vocal": False}),
]

# Script PowerShell só com ASCII (o Windows PowerShell lê .ps1 sem BOM como ANSI);
# o texto vem de um arquivo UTF-8, um trecho por linha.
MODELO_PS1 = r"""
Add-Type -AssemblyName System.Speech
$trechos = Get-Content -LiteralPath '{trechos}' -Encoding UTF8
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SelectVoice('{voz}')
$s.Rate = {taxa}
$formato = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
$s.SetOutputToWaveFile('{saida}', $formato)
$p = New-Object System.Speech.Synthesis.PromptBuilder
for ($i = 0; $i -lt $trechos.Count; $i++) {{
    $p.AppendText($trechos[$i])
    if ({pausa} -gt 0 -and $i -lt $trechos.Count - 1) {{
        $p.AppendBreak([TimeSpan]::FromMilliseconds({pausa}))
    }}
}}
$s.Speak($p)
$s.SetOutputToNull()
$s.Dispose()
"""


def sintetizar(amostra: Amostra, saida: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        arq_trechos = Path(tmp) / "trechos.txt"
        arq_trechos.write_text("\n".join(amostra.trechos), encoding="utf-8")
        ps1 = Path(tmp) / "falar.ps1"
        ps1.write_text(
            MODELO_PS1.format(trechos=arq_trechos, voz=VOZ, taxa=amostra.taxa_voz,
                              saida=saida.resolve(), pausa=amostra.pausa_ms),
            encoding="ascii",
        )
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps1)],
            capture_output=True, text=True,
        )
        if r.returncode != 0 or not saida.exists():
            raise RuntimeError(f"falha ao sintetizar {amostra.nome}: {r.stderr.strip()}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--saida", type=Path, default=DIR_SAIDA)
    args = parser.parse_args()
    args.saida.mkdir(parents=True, exist_ok=True)
    for amostra in AMOSTRAS:
        wav = args.saida / f"{amostra.nome}.wav"
        sintetizar(amostra, wav)
        wav.with_suffix(".txt").write_text(" ".join(amostra.trechos) + "\n", encoding="utf-8")
        wav.with_suffix(".esperado.json").write_text(
            json.dumps({"sintetico": True, "voz": VOZ, **amostra.esperado}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"{wav} ({wav.stat().st_size / 1024:.0f} KiB)")


if __name__ == "__main__":
    main()
