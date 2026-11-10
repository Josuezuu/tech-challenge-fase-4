# Estado

**Atualizado:** 10/11/2026 · **Marco atual:** M0 Fundação

## Decisões

| Data | Decisão | Motivo |
|---|---|---|
| 10/11 | Josué codifica; Gabriel grava os dados de teste, escreve o relatório e grava o vídeo | Grupo de dois, prazo de 7 dias |
| 10/11 | Painel em Streamlit | Mostra a fusão e o alerta chegando no vídeo |
| 10/11 | Azure for Students | Exigência nominal de Azure no áudio; crédito sem cartão |
| 10/11 | YOLOv8-pose no lugar do OpenPose | Sem GPU; mesma tarefa; o enunciado diz "modelos como" |
| 10/11 | Detectores simples (limiar, z-score robusto, regra) | Prazo, falta de dado rotulado, precisam ser explicados no vídeo |
| 10/11 | Fusão no motor de alertas por concordância de fontes | O objetivo de fusão não tem requisito; concordância é mensurável |
| 10/11 | Recall alto com teto de alertas falsos por hora | Falso negativo é o erro caro; alarme demais faz a equipe ignorar |
| 10/11 | Vídeo de cirurgia, MIMIC e AudioSet fora | Sem dado público viável no prazo; declarar no relatório |

## Bloqueios

- **Chave do Azure:** depende da conta Azure for Students (Gabriel, M0). Até lá, modo simulado.
- **Gravações V1–V5 e A1–A3:** Gabriel, até 12/11. M2 e M3 esperam por elas.

## A fazer

- [ ] Roteiros de gravação com texto exato e planilha de anotação de horários
- [ ] Criar o repositório no GitHub e convidar o Gabriel
- [ ] Conferir a região do Azure com Speech e Text Analytics for health disponíveis

## Ideias adiadas

- Textract para prescrição em imagem (disciplina da AWS)
- Isolation Forest como comparação aos detectores simples
- Webhook de alerta
- MediaPipe como comparação ao YOLOv8-pose
