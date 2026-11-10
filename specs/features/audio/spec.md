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

## Progresso

- **T1 `config.py`** — feito. `ConfigAudio` com lista curada (9 termos, severidade por termo), janelas (5 s; final < 2,5 s e janela com < 1 s de fala descartadas), VAD (25 ms, p20 + 10 dB, pausa ≥ 250 ms), faixa de F0 75–500 Hz, parâmetros padrão do Praat para jitter/shimmer, `limiar_z = 2`, `min_atributos_alterados = 2`, desvio mínimo e direção de piora por atributo. `f0_media_hz` tem direção 0 (só informativa: a spec não lhe dá direção de piora).
- **T2 `conversao.py`** — feito. ffmpeg do `imageio-ffmpeg` (`-ac 1 -ar 16000 -c:a pcm_s16le -vn`); copia `<entrada>.txt`. Teste: WAV 44,1 kHz estéreo de 2 s → 16 kHz, mono, PCM_16, 2,00 s; saída igual à entrada é recusada.
- **T3 amostras sintéticas** — feito. `scripts/gerar_audios_sinteticos.py` gera um `.ps1` ASCII e chama `powershell.exe` (`System.Speech`, `PromptBuilder` + `AppendBreak`, saída direta em 16 kHz mono PCM 16). Resultado em `data/amostras/audio/`: `sintetico_normal` 29,9 s (935 KiB), `sintetico_alterado` 49,8 s (1,5 MiB), `sintetico_termos` 15,8 s (494 KiB), cada um com `.txt` (roteiro) e `.esperado.json` (`"sintetico": true`, termos e alteração esperados).
  - `SPEC_DEVIATION: alterado com Rate = -2 (não -4) + pausas de 900 ms entre os 8 trechos — com -4 o áudio vai a 62 s (1,9 MiB) e a fala fica quase na metade da velocidade, mudança exagerada; -2 fica perto dos ~40 s pedidos e é a menor mudança que a detecção pega (ver T5). Primeiro tentei -1 (44,5 s), que não gerou alteração.`
- **T4 `termos.py`** — feito. Entidade do Azure (`SymptomOrSign`/`Diagnosis`, não negada) que contém um termo curado → `fonte_termo = "entidade"`; termo curado no texto que não sobrepõe entidade negada nem tem negação nas 3 palavras anteriores (`lexico.negado`) → `fonte_termo = "lista"`. Um evento por termo (primeira ocorrência; `ocorrencias` na evidência). Instante: casa a sequência de palavras do termo com as palavras da transcrição (k-ésima ocorrência no texto ↔ k-ésima sequência), com interpolação pela posição no texto como último recurso. 5 testes: aceite da spec (1 ALTA "falta de ar" a 3,0 s; febre negada sem evento), termo só da lista, negação pela lista e pelo Azure, palavras desalinhadas do texto (número por extenso), sentimento acima/abaixo de 0,8.
  - Decisão: um evento por termo, não por ocorrência — o motor de alertas conta eventos, e repetir "falta de ar" três vezes na mesma consulta não é três fatos.
- **T5 `acustica.py` + `comparacao.py`** — feito. Chamadas do Praat conferidas no `parselmouth` 0.4.7 (Praat 6.1.38): `To PointProcess (periodic, cc)`, `Get jitter (local)` e `Get shimmer (local)` com os parâmetros padrão (0,0001; 0,02; 1,3; 1,6), `to_harmonicity_cc()` + `Get mean` (ignora os quadros mudos de −200 dB); sem período vozeado o Praat devolve `nan`, que a comparação ignora. Janelas vão do primeiro ao último quadro de fala (silêncio de início e fim fora). `energia_db` = dBFS médio dos quadros de fala. Desvio da referência = desvio-padrão amostral das janelas com piso no `config`. 7 testes (`tests/audio/test_voz.py`).
  - **Sinal numpy** (tom harmônico de 150 Hz; normal: 75 "palavras" de 0,3 s + 0,1 s = 150 ppm, 30 s; alterado: palavras de 0,45 s e pausa de 1 s a cada 4): taxa 150,0 → 116,3 ppm (z −3,37), pausa 0,000 → 0,327 (z +10,89), pausas/min 0 → 18,7 (z +9,33) → **alteração (3 atributos)**; F0 149,7 → 150,1 (z +0,08); shimmer z −3,10 (melhora, não conta). Mesmo sinal contra ele mesmo: todos os z = 0, sem evento.
  - **Voz Maria** (transcrição simulada), normal (6 janelas) × alterado (10 janelas): taxa 149,4 → 123,7 ppm (**z −2,58**), pausa 0,013 → 0,255 (**z +7,40**), pausas/min 2,0 → 8,4 (z +1,31), F0 180,7 → 177,8 Hz (z −0,57), F0 dp 16,0 → 23,1 Hz (z +3,58, melhora), energia −22,5 → −22,8 dB (z −0,16), jitter 0,0117 → 0,0112 (z −0,23), shimmer 0,072 → 0,059 (z −1,28), HNR 17,9 → 19,1 dB (z +1,16) → **alteração (taxa + pausa)**. Normal × normal: z = 0 em tudo. Normal × termos (outro texto, mesma voz e taxa): sem alteração (só F0 dp z +2,52, que é melhora).
  - Limitação registrada: voz sintética tem jitter (~1,1 %), shimmer (~7 %) e HNR (~18 dB) praticamente constantes entre tomadas; a alteração das amostras sintéticas vem só de taxa e pausa. Jitter/shimmer/HNR só ganham sentido com as gravações A1–A3.
  - Limitação registrada: a transcrição simulada espalha as palavras uniformemente pela duração, inclusive nas pausas; isso subestima a queda da taxa por janela (com Rate -1 o z da taxa foi só −1,30 e não houve alteração; daí o Rate -2). Com o Azure real, os horários das palavras são os verdadeiros.
  - `SPEC_DEVIATION: amostra alterada final com Rate = -2 (não -4; ver T3) — 49,8 s, 1,5 MiB. Medido: Rate -1 → taxa z −1,30 (sem alteração); -2 → −2,58; -3 → −3,62; -4 → −4,20 (62 s). -2 é o menor que a detecção pega.`
- **T6 `comparacao_stt.py`** — feito. Levenshtein em palavras (uma linha da tabela por vez) após `lexico.normalizar` e troca de pontuação por espaço; referência vazia → `ValueError`. `comparar_servicos(wav, roteiro, cliente_fala, cliente_llm)` → `{"azure": {...}, "whisper": {...}}` com `wer`, `origem`, `motivo`; transcrição simulada do Azure não tem WER (seria o próprio roteiro, zero por construção); Whisper sem chave e sem gravação → `None` com motivo. 5 testes: sub/rem/ins à mão, caixa/acento/pontuação, WER 3/6 de textos conhecidos, motivos sem chave, WER 1/3 com transcrição gravada. **Sem WER medido ainda: não há chave do Azure nem da OpenAI.**
- **T7 `transcricao.py`, `analise.py`, `avaliacao.py`, `experiments/run_audio.py`** — feito. `transcricao`/`analise` são invólucros finos dos clientes de `monitor.nuvem` (transcrição vazia não chama o serviço). Novo `fluxo.py` (`processar`) junta E/S e detectores e é usado pelo runner e pela avaliação (evita duplicar o fluxo); acrescenta `audio`/`referencia` à evidência de cada evento. `comparacao_stt.wer_por_servico` reaproveita a transcrição já feita (não paga o Azure duas vezes). O runner sobrescreve `results/eventos/audio_<paciente>.jsonl` a cada execução (idempotente). 3 testes em `tests/audio/test_fluxo.py`.
  - Execução nas amostras (tudo `simulado`): `--audio sintetico_alterado --referencia sintetico_normal` → 1 evento ALTA `alteracao_vocal` (taxa z −2,58; pausa z +7,40). `--audio sintetico_termos` → `termo_critico` "falta de ar" ALTA (00:03), "dor no peito" ALTA (00:07), "tontura" INFO (00:10), febre negada sem evento, 3 `sentimento_negativo` INFO. m4a estéreo 44,1 kHz convertido e processado de ponta a ponta.
  - `--avaliar` (`results/avaliacao/audio.json`, pares normal×normal, normal×alterado, normal×termos): alteração 3/3 acertos; termos VP 3, FP 0, FN 0 (precisão 1,0, recall 1,0); WER `None` (transcrição simulada; Whisper sem chave). `so_amostras_sinteticas: true` — esses números validam o fluxo, não o desempenho em voz real.
  - Pendente para quando houver chave/gravações: WER Azure × Whisper (A1–A3 com roteiro), z de jitter/shimmer/HNR em voz real, e conferir se o Text Analytics for health em `pt` marca "falta de ar"/"tontura" como `SymptomOrSign` (senão entram por `fonte_termo = "lista"`).
  - `SPEC_DEVIATION: módulo extra fluxo.py — o runner e avaliacao.avaliar precisam do mesmo encadeamento; sem ele o fluxo ficaria duplicado.`
  - `SPEC_DEVIATION: a alteração vocal é datada no início da gravação atual (não numa janela): o z compara a tomada inteira, não um instante.`
