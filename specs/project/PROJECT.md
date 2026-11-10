# Monitoramento Multimodal de Pacientes — Tech Challenge Fase 4

**Visão:** central de monitoramento que transforma vídeo, áudio, sinais vitais e prescrições de um paciente internado em eventos com evidência, e alerta a equipe médica quando mais de uma fonte aponta para o mesmo problema.
**Para:** enfermagem do posto, médico plantonista, fisioterapeuta.
**Resolve:** o atraso entre um sinal de risco aparecer e a equipe saber, sem afogar a equipe em alarme falso.

O sistema **não diagnostica**: sinaliza um desvio com a evidência e deixa a decisão para a equipe.

## Objetivos

- **Detectar com recall alto e alarme falso limitado:** recall, precisão e alertas falsos por hora reportados por fonte, sobre anomalias plantadas com rótulo conhecido.
- **Fundir as fontes:** alerta crítico quando duas ou mais fontes concordam no mesmo paciente dentro de uma janela de 10 min; tempo até o alerta medido no cenário de ponta a ponta.
- **Usar a nuvem de verdade:** Azure Speech e Azure AI Language chamados com resposta real gravada; WER do Azure comparado ao Whisper.

## Stack

**Base:** Python 3.11, CPU (sem GPU), Windows.

**Dependências principais:**

- `ultralytics` (YOLOv8n e YOLOv8n-pose)
- `azure-cognitiveservices-speech` e `azure-ai-textanalytics` (Speech, sentimento, frases-chave, Text Analytics for health)
- `praat-parselmouth` + `numpy` (atributos acústicos da voz: F0, jitter, shimmer, HNR, energia, pausas)
- `pandas` e `numpy` (séries de sinais vitais e detectores)
- `streamlit` (painel) e `openai` (`gpt-4o-mini` para o texto do alerta, Whisper como linha de base)

## Escopo

**v1 inclui:**

- Vídeo gravado de fisioterapia (amplitude do exercício) e de quarto (saída do leito, queda, imobilidade)
- Áudio de consulta: transcrição Azure, termos críticos, sentimento, alteração vocal em relação à referência do próprio paciente
- Sinais vitais do BIDMC (PhysioNet, aberto) reproduzidos como fluxo, com limiar clínico e desvio em janela móvel
- Prescrições sintéticas com regras de anomalia
- Motor de alertas com fusão por concordância, painel Streamlit, `alertas.jsonl`
- Avaliação quantitativa por fonte gerando um único `resultados.json`

**Fora do escopo:**

- Vídeo de cirurgia, OpenPose (sem GPU), PhysioNet credenciado (MIMIC), AudioSet como voz de paciente
- Treino de modelo próprio
- Integração com prontuário, autenticação, deploy

## Restrições

- **Prazo:** entrega até 17/11/2026; plano fecha em 16/11.
- **Técnicas:** só CPU e pouca RAM; tudo roda sem chave em modo simulado com respostas gravadas.
- **Recursos:** um desenvolvedor no código; gravações, relatório e vídeo com o segundo integrante.
- **Dados:** vídeos e áudios encenados pelo grupo, com consentimento; nada de dado real de paciente.
