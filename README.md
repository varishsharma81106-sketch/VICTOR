# Victor

**The only research AI that can prove what it was allowed to see — and what it wasn't.**

## What it does

- **Epistemic status tiers** — every node carries MEASUREMENT > EXPERIMENT > LITERATURE > NOTE > HYPOTHESIS with weighted evidence aggregation
- **Masked memory with audit log** — graph structure stays live for reasoning, content withheld from LLM until explicitly unmasked. Every disclosure decision logged with caller provenance.
- **Hybrid retrieval with agent loop** — vector search + graph expansion + weighted scoring, with an LLM agent that can call reasoning tools mid-answer
- **Local-first** — runs on Ollama (no cloud required). Embeddings, LLM, and graph all operate offline.

## Install

```bash
pip install -e .
ollama pull qwen2.5:7b
```

## Quick start

```bash
victor ingest paper.md
victor ask "what claims does this paper make?"
victor gaps
```

## Security

Victor implements OWASP ASI06-aligned memory redaction. Masked nodes are excluded from retrieval and their embeddings are deleted from the vector store. All mask/unmask decisions are logged with caller provenance in a tamper-evident audit trail. This means Victor can produce a record of exactly what the AI assistant was permitted to see and when.

## Status

v5.3.0 · 212 tests passing · SciFact best: 71.0% (cross-check mode, n=100) · MCP server in progress

## License

Proprietary. See [LICENSE](LICENSE).
