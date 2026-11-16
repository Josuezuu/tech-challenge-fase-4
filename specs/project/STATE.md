# Estado

**Atualizado:** 16/11/2026 · **Marco atual:** Azure Speech e Azure AI Language rodando com chave real; 6 consultas gravadas (`data/amostras/audio/paciente_*.mp3`) nos leitos 20–25; avaliação completa gerada

## Onde está

| Feature | Status | Spec |
|---|---|---|
| Fundação | pronta | `features/fundacao/design.md` |
| Sinais vitais | pronta, avaliada nas 53 gravações reais do BIDMC | `features/sinais-vitais/spec.md` |
| Alertas e fusão | pronta | `features/alertas/spec.md` |
| Prescrições | pronta (dados sintéticos) | `features/prescricoes/spec.md` |
| Vídeo e movimentação | pronta, avaliada em 7 gravações do grupo (6/10, 0 falso positivo) e 5 clipes do UR Fall | `features/video/spec.md` |
| Áudio | pronta; Azure Speech + Language reais em 9 áudios (3 sintéticos da voz Maria, as 6 consultas `paciente_*.mp3` dos leitos 20–25, também geradas digitalmente, e as 3 gravações do Gabriel, leitos 26–28); alteração vocal validada também com voz humana (leitos 26–29: 0 alarme falso em 6 pares reais; voz cansada manipulada acusada, `leito-29`) | `features/audio/spec.md` |
| Cenário, avaliação, painel | pronta; Avaliação é uma visão separada na barra lateral (não é aba do paciente) e mostra cada vídeo gravado, anotado | `features/painel/spec.md` |

Suíte: 188 testes rápidos + 2 lentos, todos verdes (16/11).

## Decisões

| Data | Decisão | Motivo |
|---|---|---|
| 10/11 | Josué codifica; Gabriel grava os dados de teste, escreve o relatório e grava o vídeo | Grupo de dois, prazo de 7 dias |
| 10/11 | Painel em Streamlit | Mostra a fusão e o alerta chegando no vídeo |
| 10/11 | Azure for Students | Exigência nominal de Azure no áudio; crédito sem cartão |
| 10/11 | YOLOv8-pose no lugar do OpenPose | Sem GPU; mesma tarefa; o enunciado diz "modelos como" |
| 10/11 | Detectores simples (limiar, z-score robusto, regra) | Prazo, falta de dado rotulado, precisam ser explicados no vídeo |
| 10/11 | Fusão no motor de alertas por concordância de **modalidades** | O objetivo de fusão não tem requisito; concordância é mensurável; a mesma câmera não concorda consigo |
| 10/11 | Recall alto com teto de alertas falsos por hora | Falso negativo é o erro caro; alarme demais faz a equipe ignorar |
| 10/11 | Vídeo de cirurgia, MIMIC e AudioSet fora | Sem dado público viável no prazo; declarar no relatório |
| 10/11 | Respostas de nuvem gravadas e reaproveitadas sem chave | O projeto roda para quem não tem conta Azure; a demonstração não depende da rede |
| 10/11 | Sem `librosa`: atributos de voz com `numpy` + Praat | Menos dependência; o Praat mede F0, jitter, shimmer e HNR |
| 10/11 | UR Fall Detection (CC BY-NC-SA 4.0) para avaliar o vídeo | Baixável sem cadastro; substitui as gravações até elas chegarem |
| 10/11 | Vídeo anotado recodificado em H.264 para o painel | O `mp4v` do OpenCV não toca no navegador |
| 14/11 | `queda_com_recuperacao` (ALTA) além de `queda` (MAXIMA) | Cair e levantar em < 2 s ainda é queda, só não é a mais grave; vira crítico por concordância |
| 14/11 | Permanência de 2 s mantida; descida 0,4 → 0,3 | Nas gravações, o tropeço desce tanto quanto a queda (0,40 × 0,39): quem o barra é a permanência; deitar devagar fica em 0,20 |
| 14/11 | Gravações do Josué versionadas em `data/gravacoes/` | Pedido dele, com consentimento; o repositório é público |
| 14/11 | Azure via **um recurso Foundry** (`tc4-josue`, East US, grupo `rg-tech-challenge-fase4`) | O portal não oferece mais Speech e Language separados no fluxo padrão; uma chave serve aos dois |
| 14/11 | Rodar o Azure uma vez e depois usar `MONITOR_MODO_NUVEM=simulado` | Com chave, cada execução chama o serviço de novo; em `simulado` o projeto reaproveita as respostas reais gravadas |
| 15/11 | Consultas `problemas (1..6).mp3` (hoje `paciente_*.mp3`) como pacientes só de áudio, `leito-20` a `leito-25` | Consultas com queixas variadas no cenário; cada uma traz uma queixa diferente. **Correção (16/11):** são geradas digitalmente, não voz humana |
| 16/11 | Consultas renomeadas: `problemas (1)` → `paciente_6946`, `problemas (2)` → `paciente_9301`, `problemas (3)` → `paciente_2842`, `problemas (4)` → `paciente_6173`, `problemas (5)` → `paciente_7045`, `problemas (6)` → `paciente_7828` | Nome neutro de paciente; as respostas gravadas valem porque a chave é o conteúdo do áudio |
| 16/11 | Três gravações novas (`paciente_1010/8830/7870.m4a`) nos leitos 26–28, com prescrições; a 1010 é a voz de referência dos leitos 27 e 28 | Mesma pessoa (F0 média com |z| ≤ 1,6 entre elas); primeiro teste da alteração vocal com voz humana: nenhum par acusou alteração (só pausas/min passou de |z| 2; a regra pede 2 atributos), ou seja, sem alarme falso. Textos diferentes, nenhuma tomada é "cansada" de propósito |
| 16/11 | `leito-27` retirado do cenário; a `paciente_8830.m4a` continua como referência do `leito-29` e na avaliação | Pedido do Gabriel |
| 16/11 | Gabriel autoriza publicar no repositório público o vídeo `V2.mp4` (aparece nele) e as gravações de voz `paciente_1010/8830/7870.m4a` e a derivada `paciente_8830_cansada.wav` (leitos 26–29) | Consentimento registrado em `data/gravacoes/CONSENTIMENTO.md`; as consultas dos leitos 20–25 são geradas digitalmente (sem pessoa real) |
| 16/11 | `leito-29`: consulta 8830 "cansada" (fala 20% mais lenta, pausas extras, −6 dB; `experiments.gerar_voz_cansada`) contra a 8830 original; 3 pares humanos na avaliação de áudio (6/6) | Não há gravação de paciente cansado; a manipulação com gabarito prova que o detector reage ao padrão em voz humana. Declarar no relatório que é manipulada |
| 16/11 | Vídeo de fisioterapia como paciente próprio (`fisioterapia-01`, só vídeo), fora do leito-07 | Sessão de fisioterapia não é paciente de leito; sem áudio sintético nem outras fontes misturadas |
| 16/11 | Lista de termos ganha dor de cabeça, náusea, enjoo, tosse, dor abdominal, dor no estômago e as formas faladas cansado/cansada/tossir/tossindo (INFO) | Queixas das consultas reais que passavam sem evento; INFO porque são inespecíficas |

## Bloqueios

- **Áudios reais (A1–A3):** só existem as 3 amostras de voz sintética (Microsoft Maria, Windows). Com voz sintética, o Azure Speech transcreve quase perfeito e a demonstração do edital ("áudios de consultas") fica fraca. O cenário já procura `data/gravacoes/A1|A2|A3` (`.m4a` ou `.wav`) antes das amostras.

## A fazer

- [x] Primeira rodada real do Azure (15/11): Speech e Language reais no cenário e na avaliação; respostas em `docs/execucoes_gravadas/azure_*`. Usar `MONITOR_MODO_NUVEM=simulado` daqui em diante
- [x] "tossir", "tossindo", "cansado" e "cansada" na lista de termos (16/11); gabarito de `sintetico_termos` passa a esperar "cansado" (4 termos, VP 4, FP 0, FN 0)
- [x] "Aperto no peito" (ALTA), "coração acelerado" e "taquicardia" (INFO) na lista de termos (16/11); `leito-29` passa a gerar os dois alertas
- [ ] Sintoma de terceiro ("meu filho está com febre", leito-24) ainda vira termo do paciente
- [ ] Gravar A1 (voz normal), A2 (voz cansada) e A3 (consulta do leito-12: falta de ar, dor no peito, tontura); roteiros nos `.txt` de `data/amostras/audio/`
- [x] Gravar V2 (fisioterapia, elevação lateral, 16/11): paciente próprio `fisioterapia-01`, só vídeo; 6 repetições, 2 incompletas (72° e 76°), 2/2 acertos e 0 falso positivo contra a anotação
- [x] Texto dos alertas padronizado (16/11): `Alerta <NÍVEL> · <paciente> · <motivo>. <corpo da LLM> Avaliação da equipe necessária.`; 62/62 com texto da OpenAI
- [x] Rodar com as gravações do grupo (vídeo): 7 gravações, 6/10 eventos, 0 falso positivo; ver `features/video/spec.md`, seção "Gravações do grupo (14/11)"
- [ ] Conferir se o Text Analytics for health em `pt` marca "falta de ar" e "tontura" como `SymptomOrSign` (senão entram pela lista curada)
- [x] Criar o repositório no GitHub e convidar o Gabriel (`Josuezuu/tech-challenge-fase-4`, público; convite de escrita para `gaburanello` em 10/11)

## Ideias adiadas

- Textract para prescrição em imagem (disciplina da AWS)
- Isolation Forest como comparação aos detectores simples
- Webhook de alerta
- MediaPipe como comparação ao YOLOv8-pose

## Passagem para o Gabriel (14/11)

O trabalho de 14/11 está na **`main`** (veio da branch `feat/gravacoes-de-queda` por fast-forward). Para continuar: `git pull` na `main`, depois o passo a passo do README (venv, `pip install`, `python scripts/check_env.py`).

- **Chaves:** o `.env` não vai para o git. Sem ele tudo roda: a OpenAI usa as 19 respostas reais gravadas em `docs/execucoes_gravadas/openai_texto/`, e o Azure cai no simulado. As chaves (OpenAI e o recurso Azure `tc4-josue`) são do Josué; peça a ele por um canal privado, nunca pelo repositório.
- **Custo do Azure:** recurso Foundry pago por uso (sem plano grátis para o Text Analytics for health). Antes de rodar com chave, avise o Josué; depois da primeira rodada, use `MONITOR_MODO_NUVEM=simulado`. Até 14/11 foram feitas só 2 chamadas de sentimento (teste).
- **Vídeo:** câmera do quarto de lado e **alta** (1,8–2 m, inclinada para baixo). Na altura do colchão o chão em frente à cama entra no retângulo da zona do leito (a queda passou a funcionar, mas a saída do leito não sai); do alto olhando ao longo do corpo, o tronco no chão parece em pé e a queda não sai.
- **Painel:** `streamlit run app/painel.py`; os vídeos gravados ficam na visão **Avaliação do sistema** (barra lateral), seção "Vídeos avaliados". Antes, `python -m experiments.run_cenario` e `python -m experiments.run_avaliacao`.
