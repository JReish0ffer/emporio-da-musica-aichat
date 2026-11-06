# AI-assistant workflow

**Tool:** Claude Code (Anthropic's agentic coding assistant, desktop app, model Claude Sonnet 5.5), pair-programming style.
Runtime LLM of the product itself is a different thing: Groq `openai/gpt-oss-120b` (see README).

## How I used it

1. **Understand before building.** I pointed Claude Code at the challenge folder and asked it to read the brief PDF,
   the policy manual and all CSVs, then produce a structured plan (`docs/PLANO_DE_ACAO.md`, written in Portuguese since
   it was for me). The most valuable output was a **data-profiling pass** (scripted, not eyeballed) that surfaced the
   traps later encoded in `db.quality_report()` and in the tests: status/stock conflicts, inactive "Black Friday"
   promotions, totals that differ from item sums, shared e-mail between two customers, contradictions in the manual.
2. **I made the product decisions; the assistant proposed and implemented.** I reviewed and accepted the architecture
   (function calling + deterministic tools + light RAG), chose Groq as the provider, README language, and what to
   defer (final submission packaging). Ambiguities were turned into explicit, documented assumptions.
3. **Small verified increments.** Each layer was built and checked before the next: loader → tools (unit tests) → policy
   retrieval (recall on realistic questions) → agent loop → CLI → example conversations. Commits follow those steps.
4. **Run the real thing, then fix the prompt.** The first real conversations exposed problems unit tests can't catch
   (the model quoting the PIX price as the product price, dumping a 12-row installment table, offering a shopping cart
   that doesn't exist, suggesting "partner stores" that aren't in the data). I iterated on the system prompt and
   regenerated the examples with `scripts/generate_examples.py` instead of hand-writing transcripts: the files in
   `examples/` are unedited outputs of the agent.
5. **Tools used inside the assistant:** shell for running tests/scripts, file editing, PDF text extraction (`pypdf`)
   and ad-hoc Python for profiling the CSVs.

## What I'd flag honestly

- Generated code was reviewed and exercised (28 unit tests + live conversations), but it was not independently audited.
- LLM behaviour is non-deterministic: regenerating the examples can produce different wording.
