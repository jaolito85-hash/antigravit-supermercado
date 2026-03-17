# Node Data — Supermercado — Instruções para o Claude Code

## Sobre o Projeto

Node Data Supermercado é uma plataforma SaaS que coleta feedback de clientes via WhatsApp, com análise de sentimento por IA, dashboard em tempo real e inteligência de promoções competitivas para redes de supermercados.

Stack: Flask (Python), Supabase, Evolution API, OpenAI, Coolify/Docker.

**Porta:** 5003

## Estrutura do Repositório

```
server.py          — App Flask principal (maior vertical — 4500+ linhas)
Dockerfile         — Container (Gunicorn, porta 5003)
requirements.txt   — Dependências Python (inclui thefuzz, python-Levenshtein)
.env.example       — Template de variáveis de ambiente
templates/         — Dashboard (data_node.html), guia_inteligencia.html, login.html, qrcode.html
static/            — Assets estáticos
execution/         — Scripts SQL e Python, mock de produtos
directives/        — SOPs em Markdown
PRODUCTION_CHECKLIST.md — Regras de qualidade e segurança
```

## Arquitetura de Trabalho

Siga a arquitetura de 3 camadas descrita no `AGENTE.md`:
1. **Directive** (o que fazer) → arquivos em `directives/`
2. **Orchestration** (decisões) → você, o agente
3. **Execution** (fazer o trabalho) → scripts em `execution/`

## Funcionalidades Principais

- Coleta de feedback de clientes via WhatsApp
- Chatbot "Seu Pipico" com busca de produtos (fuzzy matching)
- Sistema de promoções e inteligência competitiva
- Handoff para atendimento humano (manual takeover)
- Travamento de sender (45-120s) para evitar race conditions

## Regras de Produção

Sempre siga as regras de qualidade e segurança descritas em `PRODUCTION_CHECKLIST.md` ao:
- Analisar código existente
- Sugerir mudanças
- Criar código novo
- Revisar antes de deploy

## Regras que Valem Sempre

### Segurança
- Nunca coloque chaves, tokens ou senhas no código — sempre em `.env`
- Sempre valide a origem dos webhooks recebidos
- Dados de clientes são protegidos por LGPD — nunca exponha em logs

### Código
- Sempre use try/except em chamadas externas (Supabase, Evolution API, OpenAI)
- Sempre configure timeout nas requisições HTTP (mínimo 10s)
- Sempre valide inputs antes de processar
- Sempre adicione logs nos pontos críticos
- Sempre mascare dados pessoais nos logs (telefone, CPF)
- Retorne 200 rápido nos webhooks e processe pesado em background

### Estilo
- Python com type hints quando possível
- Docstrings em português
- Nomes de variáveis descritivos em português ou inglês
- Comentários explicando o "porquê", não o "o quê"
