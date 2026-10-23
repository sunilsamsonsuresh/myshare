"""End-to-end demo: browser-less, but through every real layer.

    make dev            # API :8000, MCP server :8001, host :8002 (with ANTHROPIC_API_KEY)
    make e2e            # or: uv run --env-file .env python scripts/e2e_demo.py

    # no API key? run the host with the offline stand-in model instead of `make host`:
    uv run --env-file .env python scripts/fake_host.py

Steps:
  1. log in to the REST API as the seeded demo user
  2. POST /chat to the host: "Split ₹3,000 dinner equally with Priya and Rahul in Goa Trip"
  3. expect an `approval_required` SSE event (the graph paused at the approval node)
  4. resume the thread with {"action": "approve"}
  5. assert the expense now exists in the REST API with the right split
"""

from __future__ import annotations

import json
import os
import sys
import uuid

import httpx

API = os.environ.get("MYSHARE_API_URL", "http://localhost:8000")
HOST = os.environ.get("VITE_HOST_URL", "http://localhost:8002")
MESSAGE = "Split ₹3,000 dinner equally with Priya and Rahul in Goa Trip"


def chat(token: str, body: dict) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    with httpx.stream(
        "POST", f"{HOST}/chat", json=body, headers={"Authorization": f"Bearer {token}"}, timeout=180
    ) as r:
        r.raise_for_status()
        name = None
        for line in r.iter_lines():
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: ") and name:
                data = json.loads(line[6:])
                events.append((name, data))
                if name == "token":
                    print(data["text"], end="", flush=True)
                elif name in ("tool_call_started", "tool_call_result"):
                    status = data.get("status", "…")
                    print(
                        f"\n  [{data['phase']}] {data['tool']} {status} {data.get('summary', '')[:100]}"
                    )
                elif name == "error":
                    print(f"\n  ERROR: {data['message']}")
    print()
    return events


def main() -> None:
    login = httpx.post(
        f"{API}/auth/login", json={"email": "demo@myshare.app", "password": "password123"}
    )
    login.raise_for_status()
    token = login.json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}
    goa = next(
        g for g in httpx.get(f"{API}/groups", headers=auth).json() if g["name"] == "Goa Trip"
    )
    before = {
        e["id"]
        for e in httpx.get(
            f"{API}/expenses", params={"group_id": goa["id"], "limit": 200}, headers=auth
        ).json()
    }

    thread = f"e2e-{uuid.uuid4().hex[:8]}"
    print(f"> {MESSAGE}")
    events = chat(token, {"thread_id": thread, "message": MESSAGE})
    cards = [d for n, d in events if n == "approval_required"]
    if not cards:
        sys.exit(
            "FAIL: expected an approval card (did the model ask a clarifying question instead?)"
        )
    action = cards[0]["actions"][0]
    print(f"\nAPPROVAL CARD: {action['preview']}\n> (approving)")
    assert action["tool"] == "add_expense", action

    events = chat(token, {"thread_id": thread, "resume": {"action": "approve"}})
    assert any(
        n == "tool_call_result" and d.get("is_write") and d["status"] == "ok" for n, d in events
    ), "write failed"

    after = httpx.get(
        f"{API}/expenses", params={"group_id": goa["id"], "limit": 200}, headers=auth
    ).json()
    new = [e for e in after if e["id"] not in before]
    assert len(new) == 1, f"expected exactly one new expense, got {len(new)}"
    e = new[0]
    split = {s["user"]["name"].split()[0]: s["owed_amount"] for s in e["splits"]}
    assert e["amount"] == 300000, e["amount"]
    assert "dinner" in e["description"].lower(), e["description"]
    assert split == {"Sunil": 100000, "Priya": 100000, "Rahul": 100000}, split
    print(
        f'PASS: expense #{e["id"]} "{e["description"]}" ₹3,000.00 split {split} exists in the API.'
    )


if __name__ == "__main__":
    main()
