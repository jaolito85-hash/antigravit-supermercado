# Auditoria de Segurança — Status e Handoff

> **Última atualização:** 2026-06-26 · **Branch:** `main` · **HEAD ao pausar:** `3efa665`
> Bot WhatsApp "Seu Pipico" (Atacaforte) — entra em produção na semana de 2026-06-29.

Auditoria completa de segurança/robustez do `server.py` (entrada de mensagens via Meta
Cloud API). **11 de 14 itens corrigidos** em 7 commits atômicos. Faltam 3, todos travados
em **decisão de negócio/infra** — não em código.

---

## ✅ Itens corrigidos (commits `f160d70` → `3efa665`)

| Sev | Item | O que foi feito | Commit |
|-----|------|-----------------|--------|
| 🔴 CRÍTICO | **C1** | Webhook *fail-closed*: sem `WHATSAPP_APP_SECRET`, rejeita todos os POSTs (antes aceitava qualquer origem). Bypass só com `WEBHOOK_INSECURE_DEV=true` (dev). | `f160d70` |
| 🟠 ALTO | **A1** | `MAX_CONTENT_LENGTH = 8 MB` — anti-DoS por payload no `/webhook`. (8 MB, não 256 KB, p/ não quebrar upload de banner.) | `f160d70` |
| 🟠 ALTO | **A2** | Cache de 60s no `/api/health` — evita DoS/amplificação (a rota dispara 3 chamadas externas por hit). | `f160d70` |
| 🟡 MÉDIO | **M1** | `timeout=15s` + `max_retries=1` no construtor do cliente OpenAI (22 call sites). Antes: default de 600s do SDK. | `f160d70` |
| 🟡 MÉDIO | **M5** | Upload de banner validado por magic bytes (JPG/PNG reais) + limite de 5 MB; content-type derivado do conteúdo, não do cliente. | `f160d70` |
| 🟡 MÉDIO | **M2** | Idempotência por `message.id` (dedupe em memória, TTL 10 min) — evita reprocessar webhook reentregue. | `cb1a4f9` |
| 🔵 BAIXO | **B2** | `hmac.compare_digest` na verificação GET do webhook (era `==`, timing attack). | `def2d96` |
| 🟡 MÉDIO | **M7** | `requirements.txt` com versões pinadas (reprodutibilidade + auditabilidade de CVE). | `2748f1e` |
| 🔵 BAIXO | **B1** | `.dockerignore` — impede `.env`/`.git`/caches de entrarem na imagem via `COPY . .`. | `2748f1e` |
| 🟡 MÉDIO | **M3** | `save_json` atômico (tmp + `os.replace`) + lock por arquivo — fim da corrupção que zerava moderação/handoff. *Versão mínima* (ver pendência abaixo). | `325d0af` |
| 🔵 BAIXO | **B3** | `/api/health` não expõe mais `verified_name`/`quality_rating` da conta Business (estrutura preservada p/ não quebrar o CRM). | `c7a132d` |
| 🔵 BAIXO | **B4** | Headers de segurança (X-Frame-Options, X-Content-Type-Options, Referrer-Policy, HSTS) via `after_request`. CSP omitido de propósito. | `3efa665` |

---

## ⏳ Itens PENDENTES — retomar aqui na próxima sessão

### M4 — Rate-limit / brute-force compartilhado (MÉDIO)
**Problema:** contadores em memória por-worker (`rate_limit_store`, `daily_limit_store`,
`char_volume_store`, `_login_attempts`, `ia_moderation_warnings`, `global_message_timestamps`).
Com Gunicorn `-w 2`, limites efetivos ~2× e resetam a cada restart; dicts crescem sem
limpeza (memory leak lento).
**DECISÃO NECESSÁRIA (do usuário):**
- **(a)** rodar Gunicorn com **1 worker** — simples (1 linha no `Dockerfile`), perde paralelismo; ou
- **(b)** mover contadores para **Redis** — correto, adiciona dependência de infra.

### M6 — LGPD: retenção e exclusão (MÉDIO)
**Problema:** telefone (`feedbacks.sender`) + conteúdo das mensagens em texto puro
(Supabase + JSONs locais), sem rotina de exclusão por titular nem política de retenção.
Alguns logs imprimem trecho de conteúdo (telefone já é mascarado).
**DECISÃO NECESSÁRIA (do usuário):**
- Política de **retenção** (ex.: apagar feedbacks após 12 meses?);
- Quer **endpoint/rotina de exclusão por número** acionável pelo dashboard?

### M8 — Hardening contra prompt injection (MÉDIO)
**Problema:** texto do cliente é interpolado direto em vários prompts, incluindo o
classificador de moderação por IA (`check_message_with_ai`). Raio de impacto **limitado**
(sem tool-calling; resposta volta só ao próprio usuário; filtros de texto rodam antes).
**Correção planejada:** delimitar/escapar o input nos prompts, instruir o modelo a tratar
como dado e não instrução.
**⚠️ COORDENAR:** outro agente está trabalhando no pré-filtro de IA (ver
`TASK_PREFILTRO_IA_ATACAFORTE.md`). **Alinhar antes de tocar nesse código** para evitar conflito.

### M3 — versão completa (opcional, follow-up do já feito)
A escrita atômica resolveu a corrupção. O *lost-update* read-modify-write entre remetentes
diferentes só some migrando moderação/handoff para o Supabase (hoje são arquivos locais,
perdidos em redeploy do Coolify).

---

## ⚠️ Lembrete operacional para o deploy
O C1 tornou o webhook **fail-closed**. Confirmar que `WHATSAPP_APP_SECRET` está setado no
Coolify **antes** de subir — sem ele o bot rejeita TODAS as mensagens (seguro por design,
mas para o bot se a env faltar). Conferir também `WEBHOOK_INSECURE_DEV` **não** setado em prod.

---

## Notas de coordenação
- Outro agente atuando no mesmo repo (fluxo webhook multi-cliente + pré-filtro de IA).
- Meus commits tocaram **apenas** `server.py`, `.env.example`, `requirements.txt`, `.dockerignore`.
- `CLAUDE.md`, `templates/data_node.html` e os arquivos soltos (`FASE2-*`, `TAREFA-*`,
  `TASK_*`, `pipico-perfil.jpg`) **não** foram tocados — são do outro fluxo.
