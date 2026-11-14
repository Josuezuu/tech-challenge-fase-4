# Estado

**Atualizado:** 14/11/2026 · **Marco atual:** vídeo validado com gravações do grupo; OpenAI rodando com chave real; Azure configurado, falta a primeira rodada real

## Onde está

| Feature | Status | Spec |
|---|---|---|
| Fundação | pronta | `features/fundacao/design.md` |
| Sinais vitais | pronta, avaliada nas 53 gravações reais do BIDMC | `features/sinais-vitais/spec.md` |
| Alertas e fusão | pronta | `features/alertas/spec.md` |
| Prescrições | pronta (dados sintéticos) | `features/prescricoes/spec.md` |
| Vídeo e movimentação | pronta, avaliada em 7 gravações do grupo (6/10, 0 falso positivo) e 5 clipes do UR Fall | `features/video/spec.md` |
| Áudio | pronta, testada com voz sintética; Azure Language respondeu com a chave real (teste de 1 frase), Speech ainda não chamado | `features/audio/spec.md` |
| Cenário, avaliação, painel | pronta; aba Avaliação mostra cada vídeo gravado, anotado | `features/painel/spec.md` |

Suíte: 181 testes rápidos + 2 lentos, todos verdes (14/11).

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

## Bloqueios

- **Áudios reais (A1–A3):** só existem as 3 amostras de voz sintética (Microsoft Maria, Windows). Com voz sintética, o Azure Speech transcreve quase perfeito e a demonstração do edital ("áudios de consultas") fica fraca. O cenário já procura `data/gravacoes/A1|A2|A3` (`.m4a` ou `.wav`) antes das amostras.
- **Vídeo de fisioterapia (V2):** o leito-07 continua com o vídeo pulado.

## A fazer

- [ ] Primeira rodada real do Azure (só áudio + cenário), conferir as chamadas em tc4-josue → Monitoramento → Métricas, commitar `docs/execucoes_gravadas/azure_*` e trocar para `MONITOR_MODO_NUVEM=simulado`
- [ ] Gravar A1 (voz normal), A2 (voz cansada) e A3 (consulta do leito-12: falta de ar, dor no peito, tontura); roteiros nos `.txt` de `data/amostras/audio/`
- [ ] Gravar V2 (fisioterapia, elevação lateral) para o leito-07
- [ ] Padronizar o texto dos alertas da OpenAI (`src/monitor/alertas/redacao.py`): hoje alterna "Alerta CRÍTICO:" e "Nível: ATENÇÃO. Fonte: …"
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
- **Painel:** `streamlit run app/painel.py`; os vídeos gravados ficam na aba Avaliação, seção "Vídeos avaliados". Antes, `python -m experiments.run_cenario` e `python -m experiments.run_avaliacao`.
