# Cenário, avaliação consolidada e painel — spec

**Requisitos:** RF-69..71, RF-65..68 (consolidação) · **Marco:** M5 · **Arquivos:** `experiments/run_cenario.py`, `experiments/run_avaliacao.py`, `app/painel.py`, `data/cenario.json`

Depende de: sinais-vitais, alertas, prescrições, vídeo, áudio.

## Cenário de ponta a ponta (RF-69, RF-71)

`data/cenario.json` descreve o caso central do PRD (§5) por paciente, com cada fonte opcional:

```json
{
  "pacientes": [{
    "paciente_id": "leito-12",
    "sinais": {"gravacao": 1, "inicio": "2026-11-12T14:00:00", "plantar": ["queda_spo2@120"]},
    "video": {"arquivo": "data/gravacoes/V5.mp4", "cenario": "quarto", "inicio": "2026-11-12T14:03:30"},
    "audio": {"arquivo": "data/gravacoes/A3.m4a", "referencia": "data/gravacoes/A1.m4a", "inicio": "2026-11-13T09:00:00"},
    "prescricoes": {"dias": 5, "inicio": "2026-11-10T08:00:00"}
  }]
}
```

`python -m experiments.run_cenario [--cenario data/cenario.json]`: limpa `results/eventos/` e `results/alertas.jsonl`, roda cada fonte cujo arquivo existe (fonte com arquivo ausente é **pulada com aviso**, e a ausência aparece no resumo), passa todos os eventos pelo motor e grava os alertas. Imprime a linha do tempo e a latência do primeiro alerta crítico.

Enquanto as gravações não chegam, o cenário roda com as amostras sintéticas de áudio (`data/amostras/audio/`) e sem vídeo.

## Avaliação consolidada

`python -m experiments.run_avaliacao` chama `avaliar()` de cada feature e grava `results/resultados.json`: `{gerado_em, versao_git, sinais: {...}, prescricoes: {...}, video: {...}, audio: {...}, cenario: {...}, origens: {azure_fala, azure_linguagem, openai}}`. Fonte sem dado → `{"status": "sem_dados", "motivo": ...}`.

## Painel (RF-70)

`streamlit run app/painel.py`. Lê só `results/` (não processa mídia).

| Área | Conteúdo |
|---|---|
| Barra lateral | Pacientes com o nível mais alto de alerta (cor por nível); botão **"Reproduzir cenário"** que chama o `run_cenario` e recarrega |
| Alertas | Lista em ordem de horário: nível, regra, modalidades, texto, origem do texto; expandir mostra os eventos com as evidências |
| Sinais vitais | Gráfico das séries do paciente com as faixas clínicas e os eventos marcados |
| Vídeo | Vídeo anotado (`st.video`) e os recortes dos eventos |
| Áudio | Transcrição com termos críticos destacados, sentimento por frase, tabela de atributos de voz e z-scores, origem (Azure real/gravado/simulado) |
| Prescrições | Linha do tempo por medicamento com os itens anômalos marcados |
| Avaliação | Tabelas do `resultados.json` |

Cada área aparece só se houver dado; se não houver, mostra uma linha explicando como gerar.

Aceite: `streamlit.testing.v1.AppTest.from_file("app/painel.py").run()` sem exceção, com `results/` vazio e com `results/` gerado pelo cenário.

## Tarefas

1. `data/cenario.json` + `experiments/run_cenario.py` + teste com fontes ausentes.
2. `experiments/run_avaliacao.py` + teste do formato do `resultados.json`.
3. `app/painel.py` + teste com `AppTest` nos dois estados.
4. README: instalação, `check_env`, execução de cada fonte, cenário, painel, o que roda sem chave.

## Progresso

**Status:** concluída, 10/11/2026.

**Feito:** `src/monitor/cenario.py` (orquestração; fonte ausente é pulada e fonte com erro não derruba as outras; vídeo anotado recodificado em H.264), `data/cenario.json` (leito-12 caso central, leito-07 voz alterada e fisioterapia, leito-03 SpO2 baixa real do BIDMC 32), `experiments/run_cenario.py`, `experiments/run_avaliacao.py`, `app/painel.py`, `tests/painel/` (cenário com fontes falsas, limpeza, painel vazio e painel com cenário em todos os pacientes via `AppTest`). `gravar_evidencia` saiu do `run_sinais` para `monitor/sinais/evidencia.py`; `run_video` e `run_audio` passaram a aceitar `main(argv)`.

**Execução real** (sem chave; vídeo do leito-12 = `fall-10-cam0` do UR Fall; áudio = amostras sintéticas): 21 eventos, 18 alertas (8 críticos, 8 atenção, 2 informativos), **2 concordâncias** no leito-12 — 14:03:03 áudio + sinais vitais e 14:04:02 áudio + sinais + vídeo. A primeira concordância sai 179 s depois do primeiro evento que ela reúne. Vídeo do leito-07 pulado (sem `V2.mp4`).

**Avaliação consolidada:** as cinco seções do `results/resultados.json` com `status: ok` (sinais nas 53 gravações, vídeo nos 3 clipes do UR Fall, áudio nas 3 amostras sintéticas, prescrições, cenário).

SPEC_DEVIATION: o manifesto traz `primeira_concordancia` além de `primeiro_critico`. O primeiro crítico do cenário é uma prescrição de severidade máxima (dias antes), que não mede a fusão; o RF-69 passa a ser lido pela primeira concordância.
