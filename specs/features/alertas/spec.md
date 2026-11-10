# Alertas e fusão — spec

**Requisitos:** RO-3.4, OB-1 · RF-60..64, RF-69 · **Marco:** M1 · **Pacote:** `src/monitor/alertas/`

## Objetivo

Receber os Eventos de todas as fontes, decidir o nível do alerta (com **fusão por concordância de modalidades**) e redigir um texto curto, sem diagnóstico, com a evidência.

## Regras (RF-61)

| Nível | Quando | `regra` |
|---|---|---|
| CRÍTICO | Evento `MAXIMA` | `severidade_maxima` |
| CRÍTICO | Eventos de severidade ≥ ALTA de **duas ou mais modalidades** no mesmo paciente dentro de `janela_concordancia` (padrão 10 min) | `concordancia` |
| ATENÇÃO | Evento `ALTA` sem concordância | `severidade_alta` |
| INFORMATIVO | Evento `INFO` | `informativo` |

- **Janela** olha para trás a partir do instante do evento novo (a fila é processada em ordem de `instante`).
- **Sem repetição**: um alerta `concordancia` por paciente dentro da janela; depois de emitido, só sai outro se entrar uma modalidade nova ou a janela expirar. Alertas de outros níveis seguem um intervalo mínimo por `(paciente, tipo, nivel)` (padrão 5 min).
- O alerta carrega **todos** os eventos que o justificam (o novo + os da janela que entram na concordância).

## Requisitos e aceite

| ID | Requisito | Aceite |
|---|---|---|
| RF-60 | `MotorAlertas.processar(evento) -> list[Alerta]` e `processar_todos(eventos) -> list[Alerta]` (ordena por `instante`) | Ordem de entrada embaralhada → mesmo resultado |
| RF-61 | Regras da tabela | **No máximo um alerta por evento recebido**, pela regra de maior prioridade: `concordancia` > `severidade_maxima` > `severidade_alta` > `informativo`. SpO2 ALTA às 14:02 + queda (vídeo, MAXIMA) às 14:04 → ATENÇÃO `severidade_alta` às 14:02 e **um** CRÍTICO `concordancia` às 14:04 com os dois eventos. Duas ALTAS de vídeo e movimentação → **não** é concordância (mesma modalidade). Eventos com 11 min de distância → não é concordância |
| RF-62 | Evidências: o `Alerta.eventos` traz cada evento com sua `evidencia` intacta | Ida e volta em JSONL preserva tudo |
| RF-63 | `redacao.redigir_alerta(alerta, cliente_llm) -> (texto, origem)`: instruções de sistema proíbem diagnóstico e conduta, pedem 2–3 frases, citar fonte e horário de cada evento e terminar com "Avaliação da equipe necessária." Modelo fixo (sem chave) monta o mesmo texto por regra. **Guarda**: se o texto da LLM tiver termo proibido (`diagnóstico`, `diagnosticado`, `prescrever`, `administre`, `tem pneumonia`...) ou passar de 600 caracteres, usa o modelo fixo | Modelo fixo determinístico; guarda testada com texto ruim simulado |
| RF-64 | `saida.gravar_alertas(alertas, caminho)` → `results/alertas.jsonl`; `processar_arquivos(lista_de_jsonl) -> list[Alerta]` lê vários arquivos de eventos | Arquivo relido com `carregar_alertas` igual ao original |
| RF-69 | `latencia_ponta_a_ponta`: para o cenário, diferença entre o primeiro evento da concordância e o alerta crítico | Número no `resultados.json` |

## Entrada executável

`python -m experiments.run_alertas [--eventos results/eventos/*.jsonl] [--saida results/alertas.jsonl]` → imprime um resumo por paciente e nível.

## Tarefas

1. `config.py` (janela, intervalos, termos proibidos).
2. `motor.py` → testes do aceite RF-60/61 (cenário 14:02/14:04, mesma modalidade, janela expirada, sem repetição).
3. `redacao.py` → testes do modelo fixo e da guarda.
4. `saida.py` + `experiments/run_alertas.py` → teste de ida e volta.

## Fora

Webhook (D-2), escalonamento por tempo sem resposta, confirmação de leitura pela equipe.
