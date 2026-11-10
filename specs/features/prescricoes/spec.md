# Prescrições — spec

**Requisitos:** RO-3.2 · RF-50..53, RF-68 · **Marco:** M4 · **Pacote:** `src/monitor/prescricoes/`

## Objetivo

Detectar alterações inesperadas na evolução das prescrições de um paciente internado. Os dados são sintéticos, com anomalias plantadas e rotuladas. O texto livre da prescrição passa pelo Text Analytics for health (Azure) para extrair medicamento, dose, via e frequência, que são conferidos com o campo estruturado.

## Modelo de dados

```text
ItemPrescricao
  paciente_id, instante (datetime), medicamento (str, minúsculo, sem acento),
  dose (float), unidade (mg|g|mcg|UI|ml), via (IV|VO|SC|IM|INAL),
  intervalo_h (float), acao (inicio|manutencao|ajuste|suspensao),
  texto_livre (str, ex.: "Dipirona 1 g IV de 6/6h"), id (str)
```

Catálogo (`catalogo.py`), uns 12 medicamentos: `classe` (analgesico, opioide, anticoagulante, anti-hipertensivo, diuretico, antibiotico, insulina...), `dose_min`, `dose_max` (por administração, na unidade padrão), `unidade`, `continuo` (bool: suspensão abrupta é risco), `vias`. Valores plausíveis e **marcados no código como didáticos, não referência clínica**.

## Requisitos e aceite

| ID | Requisito | Aceite |
|---|---|---|
| RF-50 | `gerador.gerar(n_pacientes, dias, semente) -> (itens, rotulos)`: rotina plausível (início, manutenção diária, ajustes pequenos ≤ 50%) + anomalias plantadas: `dose_excessiva` (≥ 3× a anterior), `fora_da_faixa` (acima de `dose_max` ou abaixo de `dose_min`), `suspensao_abrupta` (medicamento contínuo some sem desmame), `duplicidade_classe` (dois medicamentos da mesma classe ativos ao mesmo tempo), `via_incompativel` (via fora de `vias`). Texto livre gerado a partir do item, em variações de escrita | Determinístico; cada rótulo aponta o `id` do item anômalo e o tipo |
| RF-51 | `extracao.extrair(item, cliente_linguagem) -> Extracao(medicamento, dose, unidade, via, frequencia_h, origem)` com `ClienteLinguagem.entidades_saude`; conversão de "6/6h", "8 em 8 horas", "2x ao dia" → horas; decimal com vírgula | 10 textos variados cobrindo os formatos → campos certos (modo simulado) |
| RF-52 | `regras.avaliar(historico) -> list[Evento]`, um evento `prescricao_anomala` por item anômalo; `tipo` específico (`prescricao_dose_excessiva`...), severidade: `fora_da_faixa` e `dose_excessiva` → ALTA (MAXIMA se ≥ 5× ou > 2× `dose_max`), `suspensao_abrupta` e `duplicidade_classe` → ALTA, `via_incompativel` → ALTA. Divergência entre texto livre e estruturado → INFO `prescricao_texto_divergente` | Cada tipo plantado sozinho é detectado; rotina normal → 0 eventos |
| RF-53 | Rótulos gravados em JSON junto dos itens | — |
| RF-68 | `avaliacao.avaliar(n_pacientes, dias, semente) -> dict`: recall, precisão, F1 por tipo e geral; taxa de acerto da extração (campos iguais ao estruturado) e a `origem` da extração | Reproduzível |

## Evidência

`evidencia = {"item_id": ..., "texto": "<texto livre>", "anterior": "<dose anterior> <unidade>", "extracao_origem": "real|gravado|simulado"}`.

## Entrada executável

`python -m experiments.run_prescricoes --pacientes 8 --dias 10 [--paciente leito-12 --inicio 2026-11-11T08:00:00]` → `data/amostras/prescricoes.json` (itens + rótulos) e `results/eventos/prescricao_<paciente>.jsonl`. `--avaliar` → `results/avaliacao/prescricoes.json`.

## Tarefas

1. `modelo.py` (dataclasses) + `catalogo.py`.
2. `gerador.py` → testes de determinismo e de cada anomalia plantada.
3. `extracao.py` → testes dos formatos de texto.
4. `regras.py` → testes por tipo + rotina limpa.
5. `avaliacao.py` + `experiments/run_prescricoes.py`.

## Fora

Interação medicamentosa por base externa, ajuste por função renal ou peso, OCR de receita (Textract fica como ideia adiada).

## Progresso

**Status:** concluída (tarefas 1–5), 10/11/2026.

**Feito:** `src/monitor/prescricoes/` (`modelo.py`, `catalogo.py` com 14 medicamentos marcados como didáticos, `config.py`, `gerador.py`, `extracao.py`, `regras.py`, `avaliacao.py`), `experiments/run_prescricoes.py`, `data/amostras/prescricoes.json` (259 itens, 16 rótulos, semente 42, primeiro paciente `leito-12` a partir de 11/11 08:00), `tests/prescricoes/` (47 testes: determinismo, cada anomalia plantada, 10 textos de formatos variados + 10 frequências, cada tipo detectado sozinho, rotina limpa com extração → 0 eventos, severidades, um evento por item, texto divergente INFO).

**Avaliação** (`python -m experiments.run_prescricoes --avaliar`, 8 pacientes × 10 dias, semente 42, sem chave da Azure → extração `simulado` pelo léxico):

| Métrica | Valor |
|---|---|
| Itens / textos distintos | 259 / 248 |
| Rótulos | 16 (dose_excessiva 3, fora_da_faixa 4, suspensao_abrupta 4, duplicidade_classe 3, via_incompativel 2) |
| Precisão / recall / F1 (geral e por tipo) | 1,0 / 1,0 / 1,0 |
| Extração: itens com os 4 campos certos | 1,000 (medicamento, dose, via e frequência: 1,000 cada) |
| Eventos INFO de texto divergente | 0 |

Leitura honesta desses números: as regras e o gerador usam as mesmas definições (3× a dose anterior, faixa do catálogo, desmame = redução no item anterior), então 1,0 mede **consistência** entre o que foi plantado e o que é detectado, não generalização. Num conferido de 200 sementes (8 pacientes × 10 dias cada) as regras acharam exatamente os rótulos em todas. A extração 1,0 também é do léxico simulado, que foi escrito para os mesmos formatos; o número que vale como medida é o da extração com o Text Analytics for health real (`origem = real`), que fica para quando houver chave — os 248 textos distintos viram 248 chamadas, cada uma gravada em `docs/execucoes_gravadas/azure_linguagem/`.

**Desvios da spec:**
- SPEC_DEVIATION: com mais de uma regra casando no mesmo item, vale a primeira nesta ordem: `dose_excessiva` > `fora_da_faixa` > `via_incompativel` > `suspensao_abrupta` > `duplicidade_classe` (a spec pede um evento por item, mas não diz a prioridade). Regras de dose não se aplicam a item de `suspensao`.
- SPEC_DEVIATION: "suspensão abrupta" é um item `suspensao` de medicamento contínuo cujo item anterior **não** reduziu a dose; "desmame" = o item anterior tem dose menor que o penúltimo. Medicamento que simplesmente para de aparecer, sem item de suspensão, não é detectado (não há item para o rótulo apontar).
- SPEC_DEVIATION: o gerador planta 2 anomalias por paciente, de tipos diferentes e em medicamentos diferentes, girando pela lista de tipos (`(p + k) mod 5`), e o item anômalo entra 6 h depois do item de rotina do dia (a via incompatível troca a via do próprio item de rotina). `fora_da_faixa` é sorteado entre acima de `dose_max` (1,3–1,9×) e abaixo de `dose_min` (0,5×), só onde não vira `dose_excessiva` nem faz a volta à rotina virar uma. Se um paciente não tiver lugar para um tipo (raro: ~2% em `suspensao_abrupta`), ele fica sem esse rótulo.
- `regras.avaliar(historico, extracoes=None)`: a extração é feita fora (`avaliacao.extrair_todos`, que chama o serviço uma vez por texto distinto) e entra pronta, para a regra continuar sem E/S. `gerar` aceita também `tipos`, `pacientes` e `inicio`. A evidência leva também `campos` no evento de texto divergente. `run_prescricoes` grava um `prescricao_<paciente>.jsonl` para cada um dos 8 pacientes (o de quem não tem evento fica vazio).
- A extração completa a frequência a partir do texto inteiro quando o serviço não marca a entidade `Frequency` (o léxico simulado não conhece "8 em 8 horas"); dose em g/mcg é convertida para a unidade do catálogo antes de comparar.
