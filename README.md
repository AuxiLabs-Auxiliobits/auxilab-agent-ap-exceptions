# AP Exception Handling Agent

An AI-assisted **Accounts Payable exception triage** agent. It ingests a queue of
invoice exceptions, classifies them with Claude, routes them through a
deterministic rules engine, drafts vendor/internal communications, and
prioritizes the queue for human review.

**Design principle:** AI for ambiguity (classification, drafting), deterministic
code for certainty (severity, routing rules, prioritization) — so every decision
stays reproducible and auditable.

## Quickstart

Requires Python 3.11+. **No API key needed** — with no key configured the whole
pipeline runs offline in deterministic mock mode.

```bash
git clone <repo-url>
cd auxilab-agent-ap-exceptions/Backend

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -e .

python ui.py                       # → http://localhost:7860
```

That's it. The browser opens on the agent UI — click **Load sample**, then
**Run agent**.

Prefer the terminal?

```bash
python cli.py examples/sample_exceptions.csv
```

## Using a real AI provider

Optional. Either paste a key into **⚙️ Advanced Settings** in the UI (applies
immediately, no restart), or copy `Backend/.env.example` to `Backend/.env` and
set one key there. Supported: Anthropic Claude, Google Gemini, Azure OpenAI.

See [Backend/README.md](Backend/README.md) for the pipeline, the rules engine,
the scoring model, and the full configuration reference.

## License

MIT — see [LICENSE](LICENSE).
