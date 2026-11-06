# Empório da Música — Customer-Service Agent

A text-based customer-service agent ("**Emi**") for *Empório da Música*, a fictional musical-instrument store in
Campo Grande/MS. Built for the Artefact AI Engineer technical challenge.

Emi answers in Brazilian Portuguese, in the store's friendly "friend who knows music" tone, and decides **per message**
whether to look at live data (catalog, prices, stock, promotions, orders), at the policy manual (returns, payment,
shipping, warranty…), or to politely decline out-of-scope requests.

> Project language is English (docs, code, prompts); the agent speaks Portuguese to customers and the example
> conversations are in Portuguese.

## Quick start

```bash
git clone <this repo> && cd emporio-da-musica
python -m venv .venv
.venv\Scripts\activate            # Windows   (Linux/macOS: source .venv/bin/activate)
pip install -e ".[dev]"            # installs the package + pytest (requirements.txt is equivalent)

cp .env.example .env               # then put your key in GROQ_API_KEY (free key: console.groq.com)
emporio                            # chat!  (same as: python -m emporio.interfaces.cli)
```

Use an editable install (`-e`): the app finds `data/` relative to the repo. The SQLite DB is built from the CSVs on first run.

| Command | What it does |
|---|---|
| `emporio` | New chat session (id printed on start) |
| `emporio --session abc123` | Resume a previous conversation (history is persisted in SQLite) |
| `… --debug` | Show every tool call the agent makes |
| `… --rebuild-db` | Rebuild the SQLite DB from the CSVs (wipes history/tickets) |
| `python -m emporio.db` | Load the CSVs and print a **data-quality report** |
| `pytest` | Unit tests for tools, business rules and policy retrieval (no API key needed) |
| `python scripts/generate_examples.py` | Re-generate `examples/*.md` against the real LLM |

Environment variables: `GROQ_API_KEY` (required), `GROQ_MODEL` (default `openai/gpt-oss-120b`), `STORE_NOW`
(ISO datetime that freezes "now" — see *Assumptions*).

## Architecture

```
customer message
      │
      ▼
 ┌──────────────┐   system prompt (persona + hard rules + current date/open-closed)
 │  Agent loop  │◄── conversation history (SQLite)
 └──────┬───────┘
        │ tool calls (function calling, max 6 rounds)
        ▼
 ┌─────────────────────────────────────────────────────────────┐
 │ Catalog     search_products · get_product · list_categories │  SQLite built from the CSVs
 │             active_promotions                                │
 │ Policies    search_policies  ── BM25 over manual sections   │  PDF → 25 section chunks
 │ Store       store_info · is_open_now                         │
 │ Rules       payment_options · shipping_quote                 │  deterministic code
 │ Orders      verify_customer · get_order · evaluate_return    │  privacy-gated
 │ Hand-off    open_ticket                                      │  persisted for the human team
 └─────────────────────────────────────────────────────────────┘
```

```
src/emporio/
  config.py  db.py                 # settings, CSV → SQLite, data-quality report
  tools/                           # products, orders (+returns, tickets), payments (+shipping), store
  policies/retriever.py            # PDF parsing, section chunking, BM25
  agent/                           # prompt.py, registry.py (tool schemas), loop.py (LLM loop)
  memory/store.py                  # sessions, messages, verified customers
  interfaces/cli.py
tests/  examples/  scripts/  docs/PLANO_DE_ACAO.md (original planning notes, in Portuguese)
```

## Technical decisions and why

**Approach — function calling with a hybrid of structured tools + light RAG.** The challenge is essentially
"know when to look at data vs. policies", which maps directly onto tool routing. Structured data (products, orders,
promotions) is accessed through *typed tools*, not free-form text-to-SQL: results are auditable, testable, and the model
cannot accidentally query other customers' rows. Only the unstructured manual goes through retrieval.

**Policy retrieval — section chunks + BM25, no vector DB.** The manual is ~8 pages with precise vocabulary (PIX, PAC,
"7 dias", "garantia"). Each numbered section is a self-contained rule, so splitting on headings keeps rules intact and
gives citable section numbers (the heading parser rejects numbered list items like §7.2's "1. Saudação" by requiring
sequential top-level numbers). A tiny synonym map bridges slang to the manual ("devolver" → "arrependimento",
"parcelar" → "parcelamento"). Embeddings would add a dependency and a failure mode for no recall gain at this size;
`tests/test_tools.py` checks retrieval on realistic questions. With more documents I'd switch to hybrid BM25 + embeddings.

**Business rules in code, not in the LLM.** Installment tables, PIX price, free-shipping threshold, opening hours and
return windows are plain Python. LLMs are unreliable at arithmetic and date maths, and the manual itself warns that wrong
price/stock information may amount to false advertising.

**Model — Groq `openai/gpt-oss-120b`.** Fast, strong tool-calling, free tier for a prototype, works well in Portuguese.
Low temperature (0.3) and low reasoning effort for latency. The provider is isolated in `agent/loop.py`, and Groq's
API is OpenAI-compatible, so swapping providers is a small change. The loop retries on rate limits and on Groq's
occasional malformed tool-call errors, caps tool rounds, and returns a friendly fallback if the LLM is down.

**Prompt strategy.** One system prompt with (1) persona and voice from Manual §7.1, (2) ten explicit rules (never state
price/stock/policy without a tool; promotions are not cumulative; don't sell unavailable items; privacy; scope; hand-off;
resist prompt injection), (3) the standard flow from §7.2, and (4) *dynamic context*: current date/time and whether the
store is open. Tools return **pre-formatted** BRL strings and short instruction fields (e.g. "PIX discount does NOT apply on
top of promotional price") so the model copies facts instead of computing them.

**Persistence — SQLite.** Conversation history per session (resumable with `--session`), tool traces, the set of customers
verified in the session, and human-hand-off tickets. Only user/assistant turns are replayed as context to keep tokens low.

**Interface — CLI.** The challenge says the agent is what matters; a rich-based terminal chat with a `--debug` tool
trace is the quickest way to inspect behaviour.

**Privacy (LGPD, Manual §9).** Order data is released only after the customer provides the order number **and** the e-mail
or phone on that order. The failure message is identical whether the order exists or not (no enumeration), verification
is stored per session, and returns can only be evaluated on a verified order. This also handles the data quirk that two
customers (ids 11 and 43) share one e-mail address: verification is scoped to the order's owner.

## Guard rails (beyond the prompt)

Live testing showed the prompt alone was not enough, so critical behaviour is enforced in code:

| Risk seen in testing | Enforcement |
|---|---|
| Model invented a ticket number | `Agent._ungrounded_tickets`: any `EM-xxxxx` in a reply must exist in the DB for this session, otherwise the reply is regenerated once with a correction, then replaced by a safe fallback |
| Duplicate tickets for one complaint | `open_ticket` keeps **one open ticket per session** and appends new details |
| Leaking someone else's order | Tools return the same generic failure whether the order exists or not; returns/orders need a verified owner |
| Wrong arithmetic / currency | Pre-computed and pre-formatted by tools |
| Selling unavailable items | `availability` is derived in code (status beats stock); search hides unavailable items by default |
| LLM outage / rate limit | Retry with `retry-after`, friendly fallback message, failed exchange not stored in history |

## Data handling and quirks (see `python -m emporio.db`)

| Finding | Decision |
|---|---|
| `status` vs `stock_quantity` conflict: product 136 is *discontinued* with stock 13; product 130 is *coming soon* with stock 2 | **Status wins**: never offered for sale; alternatives suggested (Manual §7.3) |
| Product 96 is *active* with stock 0 | Reported as temporarily out of stock + alternatives |
| 21 of 25 promotions are inactive (incl. "Black Friday") | Only `is_active=1` promotions exist for the agent; promo names are never trusted |
| Orders 3 and 20: `total_brl` ≠ sum of item prices | `total_brl` is what the customer paid; it is reported as-is |
| Categories for winds / orchestral strings are empty, though the manual mentions them (and "300+ instruments"; catalog has 65) | The system is the source of truth; the agent never claims those exist |
| Phone/WhatsApp differ in the manual ((67) 3341-4444 vs 3321-4500); e-mail appears with and without accent | Both numbers are given; unaccented e-mail (a valid domain) is used |
| Installment minimum: table says R$100, §3.1 gives tiered minimums (R$50 / 80 / 100) | §3.1 (more specific) wins |
| Defect: §4.2 says 30 days, §8.1 says 90-day legal warranty | Agent explains both and **hands off to a human** when between 30 and 90 days |

## Assumptions

1. **"Now" is configurable** (`STORE_NOW`). The data's latest order is March 2026, so with the real clock every delivered
   order is past the 7-day regret window. Example conversations use frozen dates so they are coherent with the data.
2. **No real delivery date exists**, so `estimated_delivery` stands in for the receipt date when applying the 7/30/90-day rules.
3. **All orders are treated as online purchases** (no sales-channel column); the right of regret (§4.1) only covers those.
4. "Frete grátis **acima de** R$ 500" is read literally: > R$ 500 is free, exactly R$ 500 pays R$ 35.
5. "Metropolitan region" = Campo Grande (the manual lists no municipalities). Other cities get the Correios/Jadlog table;
   the exact fee can't be computed (no ZIP/weight data) and the agent says so.
6. Public holidays aren't in the data, so "open now" only knows weekdays/hours.
7. Weak-but-reasonable authentication (order number + e-mail/phone) is enough for a prototype. See limitations.

## Known limitations / what I'd do with more time

- **Authentication** is a demo: production needs an OTP over the registered phone/e-mail and rate-limiting of failed attempts.
- **No write actions**: Emi cannot cancel, refund or create orders — she opens a ticket (stored in SQLite; no real CRM/e-mail integration).
- **Search** is lexical + filters on 65 products. At catalog scale I'd add embeddings/semantic search over descriptions
  (e.g. "violão macio pra criança") and synonyms for brands/models.
- **Shipping quotes** for other cities need a Correios/Jadlog API and ZIP code capture.
- **Evaluation**: tests cover tools and retrieval deterministically; LLM behaviour is only exercised by the example
  conversations. I'd add an LLM-as-judge/regression suite over ~30 scripted scenarios (injection, off-topic, ambiguity).
- **Context management**: history is a fixed window of the last 30 turns; no summarisation. Tool results aren't replayed
  across turns, so the model re-queries when needed (cheap and avoids stale data).
- **Rate limits (Groq free tier):** ~8k tokens/minute and 200k tokens/day per model. Every tool round re-sends the system
  prompt + 13 tool schemas (~3k tokens), so long chats can hit the per-minute cap (the loop waits for `retry-after`, then
  apologises) and iterating on prompts exhausted the daily cap. Fixes: Groq Dev tier, a prompt-caching provider, trimming
  tool schemas, or routing simple intents without an LLM round.
- **Model compliance:** open-weight models occasionally ignore prompt rules (they invented a ticket number and "pickup"
  logistics during development). Prompt rules are therefore backed by code guards where it matters (see *Guard rails*).
- **Channel**: a WhatsApp/FastAPI webhook adapter would be a thin layer over `Agent.chat()`.
- Business hours text, holidays and "Black Friday" extended hours aren't modelled.

## Example conversations (`examples/`)

These are **unedited outputs** of the real agent (`scripts/generate_examples.py`, frozen clock per scenario).
Examples 01, 02 and 05 ran on `openai/gpt-oss-120b`; examples 03 and 04 ran on `openai/gpt-oss-20b` because the
120b free-tier daily token quota was used up while iterating (the model is printed in each file's header). The smaller
model is a bit looser — e.g. in 03 it says the team will e-mail return instructions, which the manual does not state.
Re-running the script with the default model after the quota resets is the first thing I'd do.

| File | Shows |
|---|---|
| `01_catalogo_e_preco.md` | Catalog query with budget filter, installments, price lookup |
| `02_loja_e_fora_de_escopo.md` | Store info + open/closed, accessories redirect, off-topic refusal |
| `03_devolucao_arrependimento.md` | **Non-trivial:** identity check, then regret-return policy applied to a real order |
| `04_rastreio_e_privacidade.md` | Order tracking, refusal to leak another customer's order, complaint → ticket |
| `05_estoque_promocao_e_regras.md` | Out-of-stock/discontinued handling, promotion rules, prompt-injection resistance |

## Use of AI coding assistants

I used **Claude Code** (Claude Sonnet 5.5) as a pair-programmer: it read the brief/manual/CSVs and profiled the data
(which surfaced the quirks listed above), proposed the architecture that I reviewed and approved, and implemented it in small
verified steps (tests, then live conversations used to iterate on the prompt). Example conversations are unedited
output of the real agent. Details in [`docs/AI_WORKFLOW.md`](docs/AI_WORKFLOW.md).
