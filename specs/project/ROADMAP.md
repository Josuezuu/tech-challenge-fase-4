# Roadmap

Entrega em 17/11/2026 (terça). O plano fecha em 16/11; o dia 17 é folga.

Requisitos `RO-*` vêm do enunciado; `RF-*` e `RNF-*` são os requisitos derivados do PRD.

| Marco | Datas | Feature (`specs/features/`) | Requisitos | Depende de | Pronto quando |
|---|---|---|---|---|---|
| M0 | 10–11/11 | `fundacao` | RNF-01..05, contrato Evento/Alerta | — | `check_env` verde, `pytest` rodando, clientes Azure e OpenAI respondendo em modo simulado, BIDMC baixado por script |
| M1 | 11–12/11 | `sinais-vitais`, `alertas` | RF-40..47, RF-60..64 | M0 | Fluxo do BIDMC gera eventos; anomalias plantadas detectadas; motor emite alerta crítico quando duas fontes concordam |
| M2 | 12–13/11 | `video` | RF-01..07, RF-55..56 | M0, gravações | Queda e saída do leito detectadas nos clipes V4/V5; repetições incompletas no V2; vídeo anotado e relatório da sessão gerados |
| M3 | 13–14/11 | `audio` | RF-30..35 | M0, chave Azure, gravações | Transcrição Azure pt-BR, termos críticos no A3, desvio acústico A2 × A1, WER Azure × Whisper |
| M4 | 14/11 | `prescricoes` | RF-50..53 | M0 | Anomalias plantadas detectadas, medicamento e dose extraídos do texto livre |
| M5 | 15/11 | `painel`, `avaliacao` | RF-65..71 | M1..M4 | Painel roda o cenário de ponta a ponta; `resultados.json` alimenta todas as tabelas |
| M6 | 15–16/11 | `entrega` | EN-1..3 | M5 | README instala do zero; execuções gravadas; relatório e vídeo prontos |

## Ordem de corte se faltar tempo

1. Webhook (RF-64 opcional)
2. Whisper (RF-35)
3. Clipes opcionais V6 e A4
4. Fisioterapia (RF-03); o quarto fica
5. Extração do texto livre da prescrição (RF-51); as regras ficam

**Não se corta:** Azure, alerta com fusão, sinais vitais em fluxo, queda no vídeo, alteração vocal.
