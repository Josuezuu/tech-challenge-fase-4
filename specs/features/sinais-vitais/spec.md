# Sinais vitais — spec

**Requisitos:** RO-3.1, OB-3 · RF-40..47, RF-65 · **Marco:** M1 · **Pacote:** `src/monitor/sinais/`

## Objetivo

Reproduzir séries reais de UTI como fluxo, amostra a amostra, e emitir Eventos quando um sinal vital sai da faixa clínica ou muda bruscamente em relação ao próprio paciente. Medir recall, precisão, atraso e alertas falsos por hora sobre anomalias plantadas.

## Dados

BIDMC PPG and Respiration 1.0.0 (PhysioNet, acesso aberto). 53 gravações de ~8 min.
- URL: `https://physionet.org/files/bidmc/1.0.0/bidmc_csv/bidmc_NN_Numerics.csv` (NN = 01..53).
- Cabeçalho real: `Time [s], HR, PULSE, RESP, SpO2` (espaço depois da vírgula), 1 Hz. Pode haver `NaN` ou buraco.
- Destino: `data/raw/bidmc/`. Sem pressão arterial (ver RF-47).

## Requisitos e aceite

| ID | Requisito | Aceite |
|---|---|---|
| RF-40 | `scripts/baixar_bidmc.py [--n 53]` baixa as Numerics; `bidmc.carregar(nr) -> DataFrame` com colunas `t_s, fc, pulso, fr, spo2` (nomes limpos) | Baixa só o que falta; `carregar(1)` tem ~481 linhas e as 5 colunas numéricas |
| RF-41 | `fluxo.reproduzir(df, paciente_id, inicio, velocidade=None)` gera `Amostra(paciente_id, instante, valores: dict)` uma por vez; `velocidade=None` não dorme, `velocidade=60` dorme 1/60 s por amostra | Gera na ordem, `instante = inicio + t_s` |
| RF-42 | **Limiar clínico** por variável e nível, em `config.py`: SpO2 < 92 ALTA, < 88 MAXIMA; FC > 120 ou < 50 ALTA, > 140 ou < 40 MAXIMA; FR > 24 ou < 10 ALTA, > 30 ou < 8 MAXIMA; PA sistólica < 90 ou > 180 ALTA. Persistência mínima de N amostras (padrão 5 s) para não disparar em artefato de 1 s. Citar no código a origem das faixas: escores de alerta precoce do tipo NEWS2, sem copiar a tabela inteira | Série constante normal → 0 eventos; SpO2 em 86 por 10 s → 1 evento MAXIMA `spo2_baixa` |
| RF-43 | **Desvio do próprio paciente**: z-score robusto (mediana e MAD de uma janela móvel passada de 120 s, mínimo de 60 amostras) por variável; |z| > 4 sustentado por 5 s → Evento ALTA `<var>_desvio`. A janela usa só o passado (é fluxo) | Degrau de FC 80→105 (dentro da faixa) dispara desvio; ruído de ±2 não dispara |
| RF-44 | **Supressor**: mesmo `(paciente, tipo)` não repete antes de 300 s; reabre quando a variável volta ao normal por 30 s | Episódio contínuo de 2 min → 1 evento |
| RF-45 | `injecao.plantar(df, especificacoes, semente)` devolve `(df_copia, rotulos)`; tipos: `queda_spo2` (rampa até 82–86 e volta), `taquicardia` (+40 a +60 bpm), `bradicardia` (até 35–45), `taquipneia` (FR 30–35), `degrau_fc` (+20 a +25, dentro da faixa). Duração 30–90 s. `plantar_aleatorio(df, n, semente)` sorteia posições sem sobreposição | Original intocado; rótulos com `inicio_s, fim_s, tipo, variavel` |
| RF-46 | `MonitorVitais.processar(amostra) -> list[Evento]` mede latência de processamento (perf_counter) e guarda em `self.latencias_ms` | Média de latência disponível depois de um fluxo |
| RF-47 | `pressao_sintetica(n, semente)` gera PA sistólica 110–130 com ruído, marcada `sintetica=True` na evidência; entra só quando o chamador pede | Evento de PA traz `evidencia["sintetica"] = "sim"` |
| RF-65 | `avaliacao.avaliar(gravacoes, n_anomalias, semente) -> dict`: para cada gravação, planta anomalias, roda o fluxo e casa evento × rótulo (evento da mesma variável dentro de `[inicio, fim + 30 s]` = acerto). Recall, precisão, F1, atraso médio (s) por tipo e geral; e alertas falsos por hora rodando as séries **sem** plantio | Números reproduzíveis com a mesma semente; executa em < 1 min para as 53 gravações |

## Evidência dos Eventos

`evidencia = {"gravacao": "bidmc_01", "janela": "<t_ini>-<t_fim> s", "serie": "results/evidencias/sinais/<paciente>_<tipo>_<t>.csv"}` — o CSV tem os 120 s ao redor do evento (o painel plota dele).

## Entrada executável

`python -m experiments.run_sinais --gravacao 1 --paciente leito-12 --inicio 2026-11-12T14:00:00 [--plantar queda_spo2@120] [--velocidade 0]` → `results/eventos/sinais_vitais_<paciente>.jsonl`.
`python -m experiments.run_sinais --avaliar` → `results/avaliacao/sinais.json`.

## Tarefas

1. `config.py` com limiares, janelas e supressor documentados.
2. `bidmc.py` + `scripts/baixar_bidmc.py` → teste com CSV de 10 linhas feito à mão (colunas limpas, NaN tolerado).
3. `fluxo.py` → teste de ordem e instante.
4. `detectores.py`: `DetectorLimiar`, `DetectorDesvio`, `Supressor`, `MonitorVitais` → testes do aceite RF-42..44.
5. `injecao.py` → teste: original intocado, rótulos coerentes, determinismo.
6. `avaliacao.py` → teste com série sintética: anomalia plantada é encontrada.
7. `experiments/run_sinais.py`; rodar de verdade sobre o BIDMC baixado e registrar os números no fim desta spec.

## Fora

Modelos aprendidos (Isolation Forest fica como ideia adiada), ECG e PPG brutos (só as Numerics a 1 Hz).
