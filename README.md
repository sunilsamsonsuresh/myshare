# MyShare

A Splitwise-style expense-sharing web app, built to **learn the Model Context Protocol by building every layer by hand**: a REST API, an MCP server over it, a hand-built MCP client inside a LangGraph host, and a React chat panel that shows MCP at work.

```
React app (pages + chat) ──SSE──► Host: LangGraph + Claude + MCP client ──MCP──► MCP server ──REST──► API + SQLite
     :5173                              :8002                                      :8001              :8000
```

## Quickstart

Needs **uv**, **Node 20+**, and an **Anthropic API key**.

```bash
cd myshare
make setup                       # uv sync + npm install, creates .env from .env.example
# edit .env → ANTHROPIC_API_KEY=sk-ant-...
make seed                        # demo users, "Goa Trip" + "Flat 402", 25 expenses
make dev                         # API :8000 · MCP :8001 · host :8002 · web :5173
open http://localhost:5173       # click "Use the demo account"
```

Then click **Ask MyShare** and try:
- "Who owes me money?"
- "Add ₹1,800 for cab to Goa Trip, paid by me, split equally"
- "What's the simplest way to settle Goa Trip?"
- "Delete the last expense"

Reads run immediately. Writes show an approval card. Expand any activity chip to see the raw MCP JSON-RPC, and open the 🔌 drawer to see everything the MCP server exposes.

**No API key yet?** Run `make dev-offline` instead. It's the same stack, but the host uses a small keyword-matching stand-in for the LLM (`scripts/fake_host.py`), so everything except the language model is real.

Demo logins (password `password123`): `demo@myshare.app` (Sunil), `priya@`, `rahul@`, `ananya@myshare.app`.

## Learn MCP with this repo

| Read | What you'll learn |
|---|---|
| [`docs/MCP_EXPLAINED.md`](docs/MCP_EXPLAINED.md) | MCP from first principles, using this code: host/client/server, the three primitives, a real JSON-RPC transcript, transports, auth, prompt injection, tool design, exercises |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Diagrams, the "add expense via chat" request flow, the data model, the LangGraph state machine, every design decision |
| [`apps/mcp_server/README.md`](apps/mcp_server/README.md) | Running the MCP server alone; MCP Inspector and Claude Desktop setup |

## Commands

| | |
|---|---|
| `make dev` / `make dev-offline` | Whole stack (real Claude / offline stand-in) |
| `make api` · `make mcp` · `make host` · `make web` | One service each |
| `make test` | pytest (API, MCP server, host) + Vitest |
| `make lint` · `make typecheck` · `make fmt` | ruff + ESLint · pyright + tsc · auto-format |
| `make inspector` · `make token` | MCP Inspector against :8001, and a JWT to paste into it |
| `make e2e` | End to end: chat → approval → expense exists in the API (needs `make dev`) |
| `make injection` | Prompt-injection demo (needs `make dev`; `make seed` afterwards) |
| `uv run --env-file .env python -m myshare_host.cli` | Chat in the terminal; `-v` prints raw MCP responses; `MCP_TRANSPORT=stdio` makes the host spawn the server |

Set `MCP_DEBUG_WIRE=1` to log every JSON-RPC message the host sends and receives (stderr + `logs/mcp_wire.jsonl`).

## Layout

```
apps/api          FastAPI + SQLAlchemy REST API (source of truth: money math, auth, permissions)
apps/mcp_server   MCP server: 14 tools, 3 resources, 3 prompts; thin adapter over the API
apps/host         MCP host: hand-built MCP client + LangGraph agent + SSE chat endpoint
apps/web          React + Vite + Tailwind + Framer Motion web app (npm)
packages/shared   money helpers shared by the API and the MCP server
tests/            pytest suites for api / mcp / host
scripts/          e2e demo, injection demo, smoke test, offline host, token helper
docs/             MCP_EXPLAINED.md, ARCHITECTURE.md
```

Python 3.12+ via a **uv workspace** (each app is its own package with pinned dependencies). Frontend via **npm** in `apps/web`.

## License

[MIT](LICENSE) © 2026 Sunil Samson Suresh
