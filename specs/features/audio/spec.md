# Áudio — spec

**Requisitos:** RO-2.1..2.4 · RF-30..35, RF-67 · **Marco:** M3 · **Pacote:** `src/monitor/audio/`

## Objetivo

Processar áudio de consulta: converter, transcrever com **Azure Speech** (pt-BR), analisar a transcrição com **Azure AI Language** (sentimento, frases-chave, Text Analytics for health) para achar termos críticos, e medir **alteração vocal** pelos atributos acústicos do sinal comparados com uma tomada de referência do mesmo paciente. Whisper (OpenAI) como linha de base da transcrição.

Os clientes de nuvem já existem em `monitor.nuvem` (ver `specs/features/fundacao/design.md`); esta feature os **usa**, não os reescreve.

## Requisitos e aceite

| ID | Requisito | Aceite |
|---|---|---|
| RF-30 | `conversao.para_wav(entrada, saida=None) -> Path`: qualquer formato (m4a, mp3, mp4, ogg, wav) → WAV PCM 16 bits, mono, 16 kHz, via `imageio_ffmpeg.get_ffmpeg_exe()` em subprocesso. Copia o `<entrada>.txt` (roteiro), se existir, para junto do WAV. Saída em `results/audio/` | WAV de 44,1 kHz estéreo → 16 kHz mono |
| RF-31 | `transcricao.transcrever(wav) -> Transcricao` via `ClienteFala` | Sem chave: texto do roteiro, `origem="simulado"` |
| RF-32 | `analise.analisar(transcricao) -> AnaliseTexto` via `ClienteLinguagem.analisar` | — |
| RF-33 | `termos.detectar(analise, transcricao, paciente_id, inicio) -> list[Evento]`. **Termo crítico** = entidade de saúde **não negada** com categoria `SymptomOrSign` ou `Diagnosis` que esteja na lista curada do `config` (com severidade por termo: "dor no peito", "falta de ar", "dificuldade para respirar", "desmaio" → ALTA; "tontura", "cansaço", "fadiga", "palpitação", "febre" → INFO), comparando sem acento. Termo da lista que o Azure não marcou como entidade também conta (o Azure pode não reconhecer coloquialismo), e a evidência diz `fonte_termo = "lista"`. O instante do evento é o da primeira palavra do termo na transcrição (casar pelos horários das palavras). Frase com sentimento `negative` e `negativo ≥ 0.8` → INFO `sentimento_negativo` | "Não tenho febre, mas estou com falta de ar" → 1 evento ALTA `termo_critico` ("falta de ar"); febre negada não gera evento |
| RF-34 | **Alteração vocal**. `acustica.extrair(wav, transcricao) -> AtributosVoz` por **janelas de 5 s com fala**: `taxa_fala_ppm` (palavras da transcrição que caem na janela / tempo de fala), `proporcao_pausa` (silêncio/total; VAD por energia: quadros de 25 ms, silêncio = energia < percentil 20 + 10 dB, pausa só se ≥ 250 ms), `pausas_por_min`, `f0_media_hz`, `f0_dp_hz` (Praat via `parselmouth`, `to_pitch()`, 75–500 Hz), `energia_db`, `jitter_local`, `shimmer_local`, `hnr_db` (`parselmouth.praat.call`: "To PointProcess (periodic, cc)", "Get jitter (local)", "Get shimmer (local)", `to_harmonicity_cc()`). `comparacao.comparar(referencia, atual) -> ResultadoVoz`: z-score de cada atributo da tomada atual contra a média e o desvio das janelas da referência (desvio mínimo por atributo no `config`, para referência curta não explodir o z); **direção de piora** por atributo (taxa ↓, pausa ↑, pausas/min ↑, f0_dp ↓, energia ↓, jitter ↑, shimmer ↑, hnr ↓); alteração quando **≥ 2 atributos** pioram com |z| ≥ 2 → Evento ALTA `alteracao_vocal` (valor = nº de atributos alterados; evidência lista os atributos e os z). A descrição diz "desvio em relação à voz de referência do paciente", nunca "fadiga" ou "disartria" como diagnóstico | Áudio sintético: tom com fala a 150 ppm vs. o mesmo com pausas longas e ritmo menor → evento; o mesmo áudio contra ele mesmo → sem evento |
| RF-35 | `comparacao_stt.wer(referencia, hipotese) -> float` (distância de edição em palavras, após minúsculo, sem acento e sem pontuação); `comparar_servicos(wav, roteiro)` → WER do Azure e do Whisper (quando houver transcrição real de cada um; senão `None` com o motivo) | WER de textos conhecidos bate com o cálculo à mão |
| RF-67 | `avaliacao.avaliar(pares)` → por par (referência, atual): atributos, z, alteração sim/não; WER por serviço; termos críticos achados × esperados (quando houver `<audio>.esperado.json`) | — |

## Dados para desenvolver sem as gravações

A máquina tem a voz **Microsoft Maria (pt-BR)** do Windows. `scripts/gerar_audios_sinteticos.py` gera em `data/amostras/audio/` (versionado, pequeno, **rotulado como sintético**):
- `sintetico_normal.wav` + `.txt`: roteiro neutro, taxa normal.
- `sintetico_alterado.wav` + `.txt`: o mesmo roteiro com taxa menor (`Rate = -4`) e pausas inseridas (SSML `<break time="900ms"/>` entre frases, ou `.Rate` + silêncio concatenado).
- `sintetico_termos.wav` + `.txt`: frases com termos críticos e uma negação.

Gerar via PowerShell (`System.Speech.Synthesis.SpeechSynthesizer`, `SelectVoice("Microsoft Maria Desktop")`, `SetOutputToWaveFile`), chamado por `subprocess` a partir do script Python. Voz sintética não tem jitter/shimmer realistas: o teste da alteração vocal se apoia em taxa e pausas, e a spec registra essa limitação.

As gravações do grupo (A1–A3) chegam em `data/gravacoes/` e usam o mesmo fluxo.

## Entrada executável

`python -m experiments.run_audio --audio data/gravacoes/A2.m4a --referencia data/gravacoes/A1.m4a --paciente leito-12 --inicio 2026-11-13T09:00:00 [--whisper]` → `results/eventos/audio_<paciente>.jsonl`, `results/audio/<nome>.json` (transcrição, análise, atributos, comparação, origens). `--avaliar` → `results/avaliacao/audio.json`.

## Tarefas

1. `config.py` (lista curada com severidade, janelas, limiares, desvios mínimos).
2. `conversao.py` + teste (gera WAV estéreo 44,1 kHz com numpy/soundfile e converte).
3. `scripts/gerar_audios_sinteticos.py` → gerar e versionar as 3 amostras.
4. `termos.py` + testes (análise simulada; negação; instante pela palavra).
5. `acustica.py` + `comparacao.py` + testes (sinal sintético com numpy e as amostras da Maria).
6. `comparacao_stt.py` (WER) + testes.
7. `transcricao.py`, `analise.py`, `avaliacao.py`, `experiments/run_audio.py`; rodar nas amostras sintéticas e registrar os números no fim desta spec.

## Fora

Separação de falantes (diarização), análise em tempo real do microfone, classificação de doença pela voz.
