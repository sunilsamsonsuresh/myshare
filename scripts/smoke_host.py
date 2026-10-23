"""Smoke-test the running stack over real HTTP, with a scripted LLM (no API key needed).

    make dev   (or: make api / make mcp / make host)
    uv run --env-file .env python scripts/smoke_host.py

Exercises: login (API) -> host /chat SSE -> host MCP client -> Streamable HTTP MCP server
-> REST API, including the approval interrupt and resume. Only the LLM is fake. Prints
every SSE event so you can see the protocol the frontend consumes.

It starts its own in-process host app (so it can inject the scripted LLM) but uses the
real API on :8000 and the real MCP server on :8001.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx
from langgraph.checkpoint.memory import InMemorySaver

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from myshare_host import main as host_main  # noqa: E402
from myshare_host.graph.builder import build_graph  # noqa: E402
from myshare_host.service import ChatService  # noqa: E402
from tests.host.fake_llm import ScriptedChatModel, call, say  # noqa: E402

API = "http://localhost:8000"


async def sse(client: httpx.AsyncClient, token: str, body: dict) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    async with client.stream(
        "POST", "/chat", json=body, headers={"Authorization": f"Bearer {token}"}
    ) as r:
        name = None
        async for line in r.aiter_lines():
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: ") and name:
                data = json.loads(line[6:])
                events.append((name, data))
                short = {
                    k: v
                    for k, v in data.items()
                    if k not in ("request", "response", "structured", "details")
                }
                print(f"  event: {name:<18} {json.dumps(short, ensure_ascii=False)[:150]}")
    return events


async def main() -> None:
    api = httpx.AsyncClient(base_url=API)
    login = await api.post(
        "/auth/login", json={"email": "demo@myshare.app", "password": "password123"}
    )
    token = login.json()["access_token"]
    api.headers["Authorization"] = f"Bearer {token}"
    goa = next(g for g in (await api.get("/groups")).json() if g["name"] == "Goa Trip")["id"]
    before = len((await api.get("/expenses", params={"group_id": goa, "limit": 200})).json())

    llm = ScriptedChatModel(
        script=[
            call("get_balances", {}),
            say("You are owed money overall."),
            call(
                "add_expense",
                {
                    "description": "Smoke test cab",
                    "amount": "1800",
                    "group_id": goa,
                    "split": {"type": "equal"},
                },
                id="smoke1",
            ),
            say("Added the cab."),
        ]
    )
    host_main.app.state.chat = ChatService(
        graph=build_graph(InMemorySaver()), llm_factory=lambda: llm
    )
    transport = httpx.ASGITransport(app=host_main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://host", timeout=60) as c:
        print("1) read-only turn")
        ev = await sse(c, token, {"thread_id": "smoke", "message": "Who owes me money?"})
        assert any(n == "tool_call_result" and d["status"] == "ok" for n, d in ev)

        print("2) write turn -> approval_required")
        ev = await sse(
            c, token, {"thread_id": "smoke", "message": "Add 1800 cab to Goa, split equally"}
        )
        card = next(d for n, d in ev if n == "approval_required")
        print("   approval card:", card["actions"][0]["preview"])

        print("3) resume with approve")
        ev = await sse(
            c,
            token,
            {"thread_id": "smoke", "resume": {"decisions": {"smoke1": {"action": "approve"}}}},
        )
        assert any(
            n == "tool_call_result" and d.get("is_write") and d["status"] == "ok" for n, d in ev
        )

    after = (await api.get("/expenses", params={"group_id": goa, "limit": 200})).json()
    await api.aclose()
    assert len(after) == before + 1 and after[0]["description"] == "Smoke test cab"
    print(
        "\nOK: expense created through host -> MCP (HTTP) -> API. Run `make seed` to reset the data."
    )


if __name__ == "__main__":
    asyncio.run(main())
