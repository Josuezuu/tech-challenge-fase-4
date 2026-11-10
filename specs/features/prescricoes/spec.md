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
