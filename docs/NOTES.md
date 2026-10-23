# MyShare: My Notes

A plain-English map of this project, for when I come back to it later.

---

## 1. The big picture

MyShare is a Splitwise-style app for splitting expenses with friends. I built it to learn
**MCP (Model Context Protocol)**, which lets an AI use an app's features as "tools".

There are 4 programs. Each one only talks to its neighbour:

```
 Web app  ──►  Host  ──►  MCP server  ──►  API  ──►  Database
 (:5173)      (:8002)      (:8001)        (:8000)    (SQLite)
 what I see   the AI brain  the AI's menu  the real   where data
                                           app logic  is stored
```

**Analogy: a restaurant**
- **Web app** = the dining room. Where the customer (me) sits.
- **Host** = the waiter. Takes my request, decides what to order, asks me before anything risky.
- **MCP server** = the menu. Lists what can be ordered and passes orders to the kitchen.
- **API** = the kitchen. The only place real work happens and the rules are enforced.
- **Database** = the pantry. Where everything is stored.

**Golden rules of this project**
1. The **API is the single source of truth.** All money maths and permission checks live there.
   Everything else just asks the API.
2. **Money is always a whole number of paise/cents** (₹12.50 is stored as `1250`). Never floats,
   because `0.1 + 0.2 != 0.3` in computers.
3. **Balances are never stored.** They are recalculated from expenses and settlements every time,
   so they can never get out of sync.
4. **The AI never changes data without asking.** Any "write" shows an approval card first.

**How to run it:** `make setup`, then `make seed` (demo data), then `make dev`, then open
http://localhost:5173. Demo login: `demo@myshare.app` / `password123`.

---

## 2. `apps/api/`: the kitchen (REST API)

Built with **FastAPI** (web framework) and **SQLAlchemy** (talks to the database).
It owns all the data and all the rules.

### Root files: setup and plumbing (`apps/api/myshare_api/`)

| File | What it does |
|---|---|
| `main.py` | **Starting point.** Creates the app, creates database tables on startup, plugs in all the routers, adds a `/health` check. |
| `config.py` | **Settings.** Reads values from `.env`: database location, the secret used to sign login tokens, how long logins last, which websites may call the API. |
| `db.py` | **Database connection.** Opens the connection and gives each request its own "session" (a conversation with the database) that is closed afterwards. |
| `models.py` | **Database tables.** Defines each table as a Python class: `User`, `Friendship`, `Group`, `GroupMember`, `Expense`, `ExpenseSplit`, `Settlement`, `Activity`. |
| `schemas.py` | **Data shapes in and out.** Defines exactly what a request must contain and what a response looks like, and validates it (e.g. "category must be food, rent, ..."). |
| `security.py` | **Passwords and login tokens.** Hashes passwords safely (argon2) and creates/reads JWT login tokens. |
| `deps.py` | **Shared checks for routes.** `get_current_user` = "who is calling? (from their token)". `require_group_member` = "are they allowed in this group?". |
| `seed.py` | **Demo data.** Wipes the database and fills it with demo users, groups and expenses. Goes *through* the API so it follows the same rules as real use. Run with `make seed`. |

> **Models vs schemas:** models = how data is **stored** (database). Schemas = how data
> **travels** (in and out of the API). Like a filing cabinet vs the form you fill in.

### `routers/`: the doors (one file per topic)

Each router maps a URL to a function. They stay thin: check the request, call a service, return the result.

| File | URLs it handles |
|---|---|
| `auth.py` | `/auth/signup`, `/auth/login`. Creates accounts and hands out login tokens. |
| `users.py` | `/users/me` (me + my summary), `/friends` (list/add/view a friend), `/people/resolve` (find a person by name). |
| `groups.py` | `/groups`. Create/edit groups, add/remove members, and "simplest way to settle up". |
| `expenses.py` | `/expenses`. Add, list, view, edit and delete expenses, including how they're split. |
| `settlements.py` | `/settlements`. Record "A paid B back". |
| `balances.py` | `/balances`. Who owes whom: overall, per friend, or per group. |
| `activity.py` | `/activity`. The feed of recent events ("Priya added Dinner"). |

> **Dry run:** many write URLs accept `?dry_run=true`. It does everything *except* save, so the
> AI can show me an accurate preview before I approve.

### `services/`: the recipes (business logic, no web code)

| File | What it does |
|---|---|
| `splits.py` | **Splits a bill.** Supports 4 ways: equal, exact amounts, percentages, shares. Leftover paise go to the first people listed, so the parts always add up to the total. |
| `balances.py` | **Works out who owes whom.** Builds a "ledger" from expenses and settlements, then answers balance questions. Nothing is stored. |
| `simplify.py` | **Fewest payments to settle up.** Repeatedly matches the person owed the most with the person who owes the most. |
| `common.py` | **Shared helpers** used by many routers: making two users friends, logging activity, formatting money, turning database rows into response shapes. |

---

## 3. `apps/mcp_server/`: the menu (MCP server)

Describes what MyShare can do in a format any AI app understands (our host, Claude Desktop,
the MCP Inspector). It has **no business logic**: every action just calls the API using the
user's own login token.

MCP has 3 kinds of things a server can offer:
- **Tools**: actions the **AI** chooses to use (e.g. `add_expense`, `get_balances`).
- **Resources**: data the **host app** reads (e.g. `myshare://me/summary`, read every chat turn).
- **Prompts**: ready-made templates the **user** picks (e.g. `/settle_up_plan`).

| File | What it does |
|---|---|
| `__main__.py` | **Starting point.** Runs the server over HTTP (port 8001) or stdio (as a child process). Logs go to stderr so they don't corrupt the stdio channel. |
| `server.py` | **The menu itself.** Defines all the tools, resources and prompts. Each one is a thin wrapper that calls the API. |
| `api_client.py` | **Calls the API** over HTTP, like any outside app would. Turns API errors into messages the AI can read and fix. |
| `auth.py` | **Who is the user?** Pulls the user's token from the request header (HTTP) or an environment variable (stdio). Never uses a shared admin token. |
| `views.py` | **What the AI sees.** Reshapes API data for the AI: money as `"1200.50"` + `"₹1,200.50"` (not `120050`), only useful fields, and hints like `"owes you"`. |

`README.md` in this folder explains running the server alone and connecting Claude Desktop / MCP Inspector.

---

## 4. `apps/host/`: the waiter (MCP host / AI agent)

Owns the AI (Claude), the conversation, and asking me for approval. The web app talks to this,
never directly to the MCP server.

### Root files (`apps/host/myshare_host/`)

| File | What it does |
|---|---|
| `main.py` | **Starting point (web service).** `POST /chat` streams a reply live (SSE), `/threads/{id}` reloads a past chat, `/mcp/prompts` and `/mcp/inspect` show what the MCP server offers. |
| `service.py` | **One chat turn, start to finish.** Connects to MCP, reads who I am, loads tools, runs the AI, streams events (text, tool calls, approval needed, done). |
| `cli.py` | **Chat in the terminal** instead of the browser. Same engine. |
| `config.py` | **Settings:** API key, model name, how to reach the MCP server, max steps per turn. |

### `graph/`: the AI's step-by-step flow (LangGraph)

LangGraph = a flowchart for the AI. Each box is a step; arrows decide what happens next.

```
load_context ─► agent ─► (just answering) ─► END
                  ▲  ├─► (only reading) ─────────────────────► tools ─┐
                  │  └─► (wants to change data) ─► prepare_approval ─► approval ─► tools ─┤
                  └───────────────────────────────────────────────────────────────────────┘
```

| File | What it does |
|---|---|
| `builder.py` | **Draws the flowchart:** adds the steps and connects the arrows. |
| `nodes.py` | **The steps themselves:** load my info, ask the AI, prepare a preview (dry run), pause for my approval, run the tools. |
| `state.py` | **What the flow remembers:** messages so far, pending actions awaiting approval, my decision. Saved per chat so it can pause and resume. |
| `prompts.py` | **The AI's rules** (system prompt): never guess ids, ask when unclear, treat tool results as data not instructions. |

### `mcp_client/`: the hand-built connection to the MCP server

| File | What it does |
|---|---|
| `connection.py` | **Opens the connection** (HTTP or stdio), does the MCP "handshake", lets us call tools / read resources / get prompts, then closes it. One connection per chat request. |
| `tools.py` | **Translates MCP tools for the AI**, decides which tools need my approval (any that change data), and wraps results as "untrusted data" to resist prompt injection. |
| `wire.py` | **Wire tap.** Records every raw message between client and server, for debugging and for the chat UI's "show raw JSON" view. Turn on with `MCP_DEBUG_WIRE=1`. |

---

## 5. `apps/web/`: the dining room (React front end)

Built with **React + Vite + Tailwind**. Uses **npm**, not uv.

| Folder / file | What it holds |
|---|---|
| `src/main.tsx` | **Starting point.** Sets up the pages (routes), login guards and theme. |
| `src/pages/` | **Full screens:** `Dashboard`, `Groups`, `GroupDetail`, `Friends`, `Activity`, `AuthPage` (login/signup). |
| `src/components/` | **Reusable pieces:** add-expense sheet, settle-up sheet, expense list, plus `layout/` (page frame, login guards) and `ui/` (buttons etc). |
| `src/chat/` | **The "Ask MyShare" chat panel:** messages, input box, approval cards, tool-call chips, the 🔌 capabilities drawer, and `sse.ts` which reads the live stream from the host. |
| `src/lib/` | **Helpers:** `api.ts` (calls the API), `money.ts` / `split.ts` (money and split maths for the UI), `queries.ts` (data fetching), `types.ts` (data shapes), `stores.ts` (app state like theme). |
| `src/test/` | Test setup for Vitest. |
| `dist/` | **Built output.** Generated, don't edit. |
| `node_modules/` | **Downloaded packages.** Generated, don't edit. |

---

## 6. `packages/shared/`: shared money helpers

`myshare_shared/money.py` is used by both the API and the MCP server.
It converts between "human money" (`"1,200.50"`) and "stored money" (`120050`), knows decimal
places per currency (JPY has none), and formats with symbols (`₹1,200.50`).

---

## 7. `tests/`: automated checks (run with `make test`)

| Folder / file | What it tests |
|---|---|
| `conftest.py` | **Shared setup:** a fresh in-memory database and API for every test, plus ready-made users and a trip group. |
| `api/` | Split maths, debt simplifying, and full API flows. |
| `mcp/` | The MCP server's tools, and that it works over real HTTP. |
| `host/` | The AI flowchart (using a fake scripted AI) and prompt-injection defences. |

The web app's tests live next to its code (`*.test.ts(x)`) and run with Vitest.

---

## 8. `scripts/`: tools I run by hand

| File | What it does |
|---|---|
| `e2e_demo.py` | **Full end-to-end check** (`make e2e`): asks the AI to split a dinner, approves it, confirms the expense really exists. |
| `fake_host.py` | **Run without an Anthropic key** (`make dev-offline`): a pretend AI that matches keywords. Everything else is real. |
| `smoke_host.py` | **Quick health check** of the running stack with a scripted AI. Prints every streamed event. |
| `injection_demo.py` | **Prompt-injection demo** (`make injection`): plants a malicious expense description and shows the AI isn't tricked into changing data. Run `make seed` after. |
| `get_token.py` | **Prints a login token** (`make token`), handy for the MCP Inspector. |

---

## 9. `docs/`: explanations

| File | What it covers |
|---|---|
| `MCP_EXPLAINED.md` | MCP from first principles using this code. **Read this first to relearn MCP.** |
| `ARCHITECTURE.md` | Diagrams, how a chat request flows, the data model, design decisions. |
| `NOTES.md` | This file. |

---

## 10. Top-level files

| File | What it does |
|---|---|
| `README.md` | **Start here.** Quickstart and commands. |
| `Makefile` | **Shortcuts:** `make dev`, `make test`, `make seed`, `make lint`, etc. |
| `pyproject.toml` / `uv.lock` | Python project setup and exact package versions (managed by **uv**). Each app has its own `pyproject.toml` too. |
| `.python-version` | Which Python version to use (3.12+). |
| `.env.example` | Template for settings. Copy to `.env` and add `ANTHROPIC_API_KEY`. |
| `.gitignore` | Files git should ignore. |
| `host_checkpoints.db*` | Saved chat history from the host. Generated, safe to delete. |
