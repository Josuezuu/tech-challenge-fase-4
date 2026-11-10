# Vídeo e movimentação — spec

**Requisitos:** RO-1.1..1.3, RO-3.3 · RF-01..07, RF-55..56, RF-66 · **Marco:** M2 · **Pacotes:** `src/monitor/video/`, `src/monitor/movimentacao/`

## Objetivo

Processar vídeo **gravado** em CPU, extrair pose (17 pontos COCO) e objetos (leito, cadeira) com YOLOv8, e transformar a sequência em Eventos em dois cenários: **fisioterapia** (amplitude do exercício) e **quarto** (saída do leito, queda, imobilidade, movimentação atípica). Gerar vídeo anotado, recortes de quadro como evidência e o relatório automático da sessão.

## Decisão de modelo

YOLOv8n-pose (`models/yolov8n-pose.pt`) e YOLOv8n (`models/yolov8n.pt`, classes COCO `bed`=59, `chair`=56 — conferir em `model.names`) no lugar do OpenPose: sem GPU nesta máquina, mesma tarefa (pose de várias pessoas), e o enunciado diz "modelos **como**". API conferida em `ultralytics==8.4.208`: `r = YOLO(p)(frame, verbose=False)[0]`; `r.keypoints.xy` (N,17,2), `r.keypoints.conf` (N,17), `r.boxes.xyxy`, `r.boxes.cls`, `r.boxes.conf`, `r.names`.

Índices COCO: 0 nariz, 5/6 ombros E/D, 7/8 cotovelos, 9/10 punhos, 11/12 quadris, 13/14 joelhos, 15/16 tornozelos.

## Arquitetura (o que é puro e o que tem E/S)

| Módulo | E/S? | Papel |
|---|---|---|
| `video/leitura.py` | sim | Itera quadros amostrados a `fps_alvo` (padrão 5) com `t_s`; metadados (fps, tamanho, duração) |
| `video/inferencia.py` | sim | Roda YOLO pose + detecção por quadro → `QuadroAnalisado(t_s, pessoas: list[Pessoa], objetos: list[Objeto])`. **Cache** em `results/cache_video/<hash do arquivo + fps>.json` para não rodar o modelo duas vezes |
| `video/geometria.py` | não | Ângulo de três pontos, centro do quadril, inclinação do tronco em relação à vertical, altura do corpo, normalização pela altura da caixa, suavização (mediana móvel) |
| `video/paciente.py` | não | Escolhe **o paciente** quando há mais de uma pessoa: rastreamento simples por proximidade do centro ao quadro anterior; o primeiro é a pessoa mais perto do leito (ou a maior caixa) |
| `video/fisioterapia.py` | não | Máquina de estados de repetições sobre o ângulo do exercício |
| `video/quarto.py` | não | Zonas e eventos de quarto |
| `movimentacao/serie.py`, `movimentacao/detector.py` | não | Série de movimentação por janela e desvio do padrão |
| `video/anotacao.py` | sim | Vídeo anotado (`.mp4`) e recortes `.jpg` de cada evento |
| `video/relatorio.py` | sim | Relatório da sessão em Markdown |

## Requisitos e aceite

| ID | Requisito | Aceite |
|---|---|---|
| RF-01 | Leitura amostrada com `t_s` | Vídeo de 10 s a 30 fps, `fps_alvo=5` → ~50 quadros com `t_s` crescente |
| RF-02 | Inferência com cache; pontos com confiança < 0.3 viram `NaN` | Segunda execução lê o cache (teste com `lento`) |
| RF-03 | **Fisioterapia**, exercício `elevacao_lateral` (padrão): ângulo quadril–ombro–cotovelo do lado mais visível. Repetição começa quando o ângulo passa de `limiar_inicio` (padrão 30°) e termina quando volta abaixo dele; o pico da repetição < `amplitude_esperada` (padrão 80°) → Evento INFO `amplitude_insuficiente` (valor = pico). Ao fim: contagem total e de incompletas. Exercício `agachamento` (ângulo quadril–joelho–tornozelo, amplitude = menor ângulo, esperado ≤ 100°) como segunda opção | Série sintética com 10 repetições, 3 com pico 55° → 10 repetições e 3 eventos |
| RF-04 | **Quarto**. Zona do leito: caixa `bed` mediana dos primeiros quadros, ampliada em 10%; ou polígono do `config` quando o modelo não acha o leito. `saida_do_leito` (ALTA, `Fonte.MOVIMENTACAO`): centro do quadril estava na zona por ≥ 3 s e fica fora por ≥ 3 s. `queda` (MAXIMA, `Fonte.VIDEO`): inclinação do tronco > 60° da vertical **e** queda do centro do quadril > 0,4 altura do corpo em ≤ 1,5 s **e** fora da zona do leito **e** permanece baixo/horizontal por ≥ 2 s. `imobilidade_prolongada` (ALTA, `MOVIMENTACAO`): deslocamento médio dos pontos < limiar por ≥ `imobilidade_s` (padrão 60 s na demonstração; o `config` explica que o valor clínico seria em horas). `paciente_ausente` (INFO): ninguém no quadro por ≥ 10 s | Sequências sintéticas de pontos: deitar → sem evento; levantar e sair → 1 `saida_do_leito`; queda → 1 `queda` (e não dispara ao deitar devagar **na cama**); parado 70 s → 1 `imobilidade_prolongada` |
| RF-05 | Vídeo anotado: esqueleto, caixa do leito/zonas, rótulo de estado e eventos sobrepostos no tempo em que ocorrem; `results/evidencias/video/<nome>_anotado.mp4` (codec `mp4v`) | Arquivo abre com OpenCV e tem a mesma duração (na taxa amostrada) |
| RF-06 | Relatório da sessão: tabela de eventos (horário, tipo, valor) + texto de 1 parágrafo via `ClienteLLM.redigir` com modelo fixo; para fisioterapia inclui repetições totais/incompletas e amplitude média. `results/relatorios/<nome>.md`, com links para os recortes | Sem chave sai o texto do modelo fixo |
| RF-07 / RF-55 | `movimentacao.serie.calcular(quadros, janela_s=10)` → DataFrame por janela: `movimento` (deslocamento médio normalizado dos pontos), `no_leito` (fração do tempo na zona), `presente` (fração com paciente) | Série de quadros feita à mão → valores esperados |
| RF-56 | `movimentacao.detector`: z-score robusto do `movimento` contra as janelas anteriores do mesmo vídeo (mínimo 6 janelas); |z| > 4 → INFO `movimentacao_atipica` (agitação). Os eventos do RF-04 de movimentação saem daqui também | Pico de agitação numa série calma → 1 evento |
| RF-66 | `avaliacao.avaliar(anotacoes_json)`: para clipes com anotação (`data/gravacoes/anotacoes.json`: `{arquivo: {cenario, eventos: [{tipo, t_s}]}}`), acerto por evento (tolerância ±2 s), falsos positivos; clipes sem anotação são pulados com aviso | Teste com anotação e eventos feitos à mão |

## Dados para desenvolver sem as gravações

As gravações do grupo (V1–V5) chegam até 12/11 em `data/gravacoes/`. Até lá:
1. **Testes de lógica** com sequências de pontos sintéticas (`tests/video/sintetico.py`: gera pose de pessoa em pé, deitada, levantando, caindo, braço subindo até X graus).
2. **Teste de integração** (`lento`): vídeo curto montado a partir de `ultralytics.utils.ASSETS / "bus.jpg"` com OpenCV, só para provar que leitura → inferência → anotação roda ponta a ponta.
3. Se um conjunto público de quedas for **baixável sem cadastro e com licença de uso acadêmico** (ex.: UR Fall Detection Dataset), um script opcional `scripts/baixar_quedas.py` com a URL e a licença registradas; se não for, registrar a conclusão no fim desta spec e seguir sem ele.

## Entrada executável

`python -m experiments.run_video --video data/gravacoes/V5.mp4 --cenario quarto --paciente leito-12 --inicio 2026-11-12T14:03:30 [--fps 5]` → `results/eventos/video_<paciente>.jsonl`, `results/eventos/movimentacao_<paciente>.jsonl`, vídeo anotado, recortes e relatório. `--cenario fisioterapia --exercicio elevacao_lateral`. `--avaliar` → `results/avaliacao/video.json`.

## Tarefas

1. `config.py` de cada pacote.
2. `geometria.py` + testes.
3. `tests/video/sintetico.py` (gerador de poses).
4. `fisioterapia.py` + testes.
5. `paciente.py` + `quarto.py` + testes.
6. `movimentacao/` + testes.
7. `leitura.py`, `inferencia.py` (cache), `anotacao.py` + teste `lento` com o vídeo montado de `bus.jpg`.
8. `relatorio.py` + `experiments/run_video.py` + `avaliacao.py`.
9. Rodar o teste `lento` e registrar tempo por quadro em CPU no fim desta spec.

## Fora

Vídeo de cirurgia, OpenPose, treino de modelo, rastreamento com ReID, câmera ao vivo.

## Progresso

- **T1 config** — `video/config.py` (`ConfigInferencia`, `ConfigPaciente`, `Exercicio` + `EXERCICIOS`, `ConfigFisioterapia`, `ConfigQuarto`) e `movimentacao/config.py` (`ConfigMovimentacao`).
  - SPEC_DEVIATION: `video/tipos.py` (novo) guarda `Pessoa`, `Objeto`, `QuadroAnalisado`; motivo: os módulos puros usam esses tipos e não devem importar o YOLO de `inferencia.py`.
- **T2 geometria** — ângulo, centro do quadril/ombros, inclinação do tronco, tamanho do corpo (maior lado da caixa, não depende da orientação), deslocamento médio, mediana móvel, ampliação de caixa, ponto no polígono. 6 testes.
- **T3 sintético** — `tests/video/sintetico.py`: postura (quadril, inclinação, braço) → 17 pontos COCO; cenas prontas da spec.
- **T4 fisioterapia** — máquina de estados; 10 repetições com 3 de pico 55° → 10 e 3 eventos. Agachamento testado com série de ângulos.
  - SPEC_DEVIATION: a repetição termina a `histerese` (5°) aquém do limiar, não exatamente no limiar; motivo: tremor do esqueleto em torno de 30° contaria repetições falsas.
  - Achado: a mediana de 3 quadros corta um pico de um quadro só; a série sintética segura o pico 0,6 s (como no exercício real).
- **T5 paciente + quarto** — `paciente.py` (regra inicial: mais perto do leito ou maior caixa; depois o mais próximo, até 1 corpo por quadro; perdeu por 3 s, escolhe de novo). `quarto.py`: zona, `EstadoQuadro` por quadro, `detectar_quedas`, `detectar_ausencia`. 11 testes: queda → 1 evento (descida 0,49 corpo); deitar devagar na cama, deitar devagar no chão, o mesmo movimento da queda caindo sobre o leito, queda com recuperação em 0,6 s e queda no fim do vídeo sem 2 s para confirmar → nenhum.
  - Decisão: `saida_do_leito` e `imobilidade_prolongada` (`Fonte.MOVIMENTACAO`) saem de `movimentacao/detector.py`, como diz o RF-56; `queda` e `paciente_ausente` (`Fonte.VIDEO`) saem de `quarto.py`.
  - Decisão: "tamanho do corpo" = maior lado da caixa (altura em pé, comprimento deitado), régua igual antes e depois da queda.
- **T6 movimentação** — `serie.calcular(estados, janela_s)` e `detector.detectar` (saída do leito, imobilidade, agitação). 8 testes: série feita à mão; deitar → nada; levantar e sair → 1 `saida_do_leito`; virar na borda 1 s → nada; parado 70 s → 1 `imobilidade_prolongada`; 50 s → nada; 10 s de agitação depois de 2 min calmos → 1 `movimentacao_atipica`; menos de 6 janelas de histórico → nada.
  - SPEC_DEVIATION: agitação só com z > +4 (a spec diz |z| > 4); motivo: z muito negativo é o paciente sossegando (ex.: dormiu depois de andar), e a falta de movimento já tem o evento `imobilidade_prolongada`.
  - Decisão: piso de 0,01 corpo/s no MAD, senão uma série calma quase constante dá z infinito ao menor movimento.
  - Decisão: velocidade = deslocamento médio dos pontos ÷ tamanho do corpo ÷ intervalo entre quadros (corpos/s, não depende do fps); imobilidade usa a mediana móvel de 5 quadros dessa velocidade.
  - Decisão: `instante` = começo do fato (quando saiu, quando parou, quando sumiu); `valor` = medida (duração ou z).
- **T7 leitura, inferência, anotação** — `leitura.py` (amostragem por `grab`, só decodifica o quadro usado), `inferencia.py` (`Analisador` com os dois YOLO; cache em `results/cache_video/<sha256 do arquivo + fps + pesos + limiares>.json`), `anotacao.py` (uma passada: zona, objetos, esqueletos — paciente em verde —, rótulo do quadro, faixa vermelha 3 s depois de cada evento, `.jpg` do primeiro quadro de cada evento). Testes rápidos com vídeo sintético preto (10 s a 30 fps → 50 quadros; anotado com 78 quadros a 5 fps e recorte da queda). Teste `lento` com `bus.jpg` (3 s a 10 fps → 15 quadros, ≥ 3 pessoas por quadro, cache na 2ª execução).
  - SPEC_DEVIATION: `video/pipeline.py` (novo) orquestra a sessão; motivo: o `run_video`, o `--avaliar` e o teste `lento` chamam o mesmo fluxo.
  - Os recortes ficam em `results/evidencias/video/<nome>/NN_<tipo>_<t>s.jpg`; o OpenCV não escreve acento, então o texto sobreposto sai sem acento.
- **T8 relatório, run_video, avaliação** — `relatorio.py` (`dados_da_sessao` → `ClienteLLM.redigir` com `texto_modelo_fixo`; tabela de eventos com link relativo ao recorte), `avaliacao.py` (`avaliar(anotacoes, detectados, tolerancia_s=2)`: acertos, falsos positivos, perdidos, sensibilidade e precisão por tipo; clipe sem anotação pulado com aviso), `experiments/run_video.py`. 3 testes rápidos.
- **T9 medição** — `pytest -q`: 38 testes de vídeo rápidos (suíte inteira 119 passed, 2 deselected); `pytest -m lento`: 2 passed (~11 s).
  - **Tempo por quadro em CPU** (YOLOv8n-pose + YOLOv8n, os dois por quadro, sem GPU): 0,07 s (640×240) a 0,10 s (810×1080, `bus.jpg`) em regime; média da execução com o aquecimento do 1º quadro, em clipe curto: 0,21–0,36 s. A 5 quadros/s analisados, 1 s de vídeo custa ~0,35–0,5 s de CPU: mais rápido que o tempo real.
  - Correção achada nos clipes públicos (com teste): a janela de permanência da queda que termina entre dois quadros amostrados agora confirma no quadro seguinte; e quadro com a pessoa presente mas sem quadril nem ombros medidos não conta contra a confirmação.

### Conjunto público de quedas (UR Fall Detection Dataset)

- **Baixável sem cadastro, licença CC BY-NC-SA 4.0 (uso acadêmico não comercial)**, http://fenix.ur.edu.pl/~mkepski/ds/uf.html, citação Kwolek e Kępski (2014). `scripts/baixar_quedas.py` baixa só a câmera frontal (`*-cam0.mp4`, 640×240 com profundidade à esquerda e RGB à direita, 30 fps, ~1 MB cada) e gera `data/raw/urfall/anotacoes.json` a partir do CSV oficial de rótulos (queda = 1º quadro "deitado no chão").
- Clipes usados: `fall-01`, `fall-10` (quedas) e `adl-01` (sentar; controle negativo). `python -m experiments.run_video --avaliar --anotacoes data/raw/urfall/anotacoes.json`:
  - `fall-10`: queda detectada a 2,2 s (anotada 2,3 s), descida 0,50 corpo, tronco a 77°. Acerto.
  - `fall-01`: **perdida** com os parâmetros da spec. Todos os critérios de queda se cumprem a 3,6 s (anotada 3,73 s; descida 0,56 corpo, tronco 67°), mas o clipe acaba 1,6 s depois, antes dos 2 s de permanência. Com `queda_permanencia_s=1,5` ou `1,0` ela é detectada a 3,6 s.
  - `adl-01`: nenhum evento (tronco chega a 54°, quadril desce 0,34 corpo: abaixo dos dois limiares).
  - Resultado: sensibilidade 1/2, precisão 1/1, 0 falso positivo (`results/avaliacao/video.json`).
- Limite do conjunto: os clipes são cortados logo depois da queda. Pelo CSV, dos 30 clipes de queda, só 2 têm ≥ 2 s de "deitado" até o fim (mediana 0,7 s). Ele serve para conferir descida e inclinação, não a permanência; a permanência de 2 s fica para as gravações do grupo (V1–V5). O padrão segue 2 s, como na spec.
