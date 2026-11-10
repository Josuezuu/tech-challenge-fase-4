# Estado

**Atualizado:** 10/11/2026 · **Marco atual:** código de M0–M5 pronto; falta rodar com chave do Azure e com as gravações do grupo

## Onde está

| Feature | Status | Spec |
|---|---|---|
| Fundação | pronta | `features/fundacao/design.md` |
| Sinais vitais | pronta, avaliada nas 53 gravações reais do BIDMC | `features/sinais-vitais/spec.md` |
| Alertas e fusão | pronta | `features/alertas/spec.md` |
| Prescrições | pronta (dados sintéticos) | `features/prescricoes/spec.md` |
| Vídeo e movimentação | pronta, avaliada em 3 clipes do UR Fall | `features/video/spec.md` |
| Áudio | pronta, testada com voz sintética | `features/audio/spec.md` |
| Cenário, avaliação, painel | pronta | `features/painel/spec.md` |

Suíte: 171 testes rápidos + 2 lentos, todos verdes.

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

## Bloqueios

- **Chave do Azure** (Speech e Language): sem ela, transcrição e análise de texto rodam no modo simulado. Com a chave, rodar `python -m experiments.run_cenario` e `run_avaliacao` grava as respostas reais em `docs/execucoes_gravadas/`, que entram no git.
- **Gravações do grupo** (V1–V5, A1–A3) em `data/gravacoes/` com `anotacoes.json`: o cenário já procura por elas antes das amostras públicas e sintéticas.

## A fazer

- [ ] Rodar com a chave do Azure e commitar as respostas gravadas
- [ ] Rodar com as gravações do grupo; ajustar limiares de vídeo se preciso, registrando antes e depois
- [ ] Conferir se o Text Analytics for health em `pt` marca "falta de ar" e "tontura" como `SymptomOrSign` (senão entram pela lista curada)
- [ ] Criar o repositório no GitHub e convidar o Gabriel

## Ideias adiadas

- Textract para prescrição em imagem (disciplina da AWS)
- Isolation Forest como comparação aos detectores simples
- Webhook de alerta
- MediaPipe como comparação ao YOLOv8-pose
