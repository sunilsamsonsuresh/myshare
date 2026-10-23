"""Chat with the MyShare agent from the terminal: the whole MCP stack, no browser.

    uv run --env-file .env python -m myshare_host.cli                       # interactive
    uv run --env-file .env python -m myshare_host.cli "Who owes me money?"  # one message
    MCP_TRANSPORT=stdio ... python -m myshare_host.cli                        # host launches the server

Needs the REST API running (to log in) and, for MCP_TRANSPORT=http, the MCP server.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from typing import Any

import httpx
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from .config import get_settings
from .graph.builder import build_graph
from .service import ChatService, TurnRequest

DIM, BOLD, GREEN, RED, YELLOW, RESET = (
    "\033[2m",
    "\033[1m",
    "\033[32m",
    "\033[31m",
    "\033[33m",
    "\033[0m",
)


def login(email: str, password: str) -> str:
    api = get_settings().myshare_api_url
    r = httpx.post(f"{api}/auth/login", json={"email": email, "password": password}, timeout=10)
    if r.status_code != 200:
        sys.exit(f"Login failed ({r.status_code}): {r.text}")
    return r.json()["access_token"]


def ask_decision(actions: list[dict[str, Any]]) -> dict[str, Any]:
    decisions: dict[str, Any] = {}
    for a in actions:
        flag = f"{RED}(destructive){RESET} " if a["destructive"] else ""
        print(f"\n{YELLOW}{BOLD}Approval needed{RESET} {flag}{a['title']}\n  {a['preview']}")
        choice = input("  [a]pprove / [r]eject / [e]dit? ").strip().lower()[:1]
        if choice == "a":
            decisions[a["tool_call_id"]] = {"action": "approve"}
        elif choice == "e":
            decisions[a["tool_call_id"]] = {
                "action": "edit",
                "feedback": input("  What should change? "),
            }
        else:
            decisions[a["tool_call_id"]] = {
                "action": "reject",
                "feedback": input("  Reason (optional): "),
            }
    return {"decisions": decisions}


async def turn(
    svc: ChatService, token: str, req: TurnRequest, verbose: bool
) -> list[dict[str, Any]] | None:
    """Run one turn, printing events. Returns pending actions if the graph paused."""
    pending = None
    async for ev in svc.run(token, req):
        kind = ev["event"]
        if kind == "token":
            print(ev["text"], end="", flush=True)
        elif kind == "resource_read":
            print(f"{DIM}[resources/read {ev['uri']}]{RESET}")
        elif kind == "tool_call_started":
            label = "dry run" if ev["phase"] == "preview" else "tools/call"
            print(
                f"{DIM}[{label} {ev['tool']} {json.dumps(ev['args'], ensure_ascii=False)}]{RESET}"
            )
        elif kind == "tool_call_result":
            mark = f"{GREEN}✓{RESET}" if ev["status"] == "ok" else f"{RED}✗ {ev['status']}{RESET}"
            print(f"{DIM}  {mark}{DIM} {ev.get('summary', '')[:160]}{RESET}")
            if verbose and ev.get("response"):
                print(f"{DIM}  <- {json.dumps(ev['response'], ensure_ascii=False)[:600]}{RESET}")
        elif kind == "approval_required":
            pending = ev["actions"]
        elif kind == "error":
            print(f"\n{RED}error: {ev['message']}{RESET}")
        elif kind == "done":
            print()
    return pending


async def main_async(args: argparse.Namespace) -> None:
    token = login(args.email, args.password)
    settings = get_settings()
    print(
        f"{DIM}Logged in as {args.email}. MCP transport: {settings.mcp_transport}. Model: {settings.model_name}{RESET}"
    )
    async with AsyncSqliteSaver.from_conn_string(settings.host_checkpoint_db) as saver:
        svc = ChatService(graph=build_graph(saver))
        thread = args.thread or f"cli-{uuid.uuid4().hex[:8]}"
        messages = [args.message] if args.message else None
        while True:
            # input() blocks, so run it in a thread instead of stalling the event loop.
            text = (
                messages.pop(0)
                if messages
                else (await asyncio.to_thread(input, f"\n{BOLD}you>{RESET} ")).strip()
            )
            if not text or text in {"exit", "quit"}:
                break
            pending = await turn(
                svc, token, TurnRequest(thread_id=thread, message=text), args.verbose
            )
            while pending:
                decision = await asyncio.to_thread(ask_decision, pending)
                pending = await turn(
                    svc, token, TurnRequest(thread_id=thread, resume=decision), args.verbose
                )
            if args.message:
                break


def main() -> None:
    p = argparse.ArgumentParser(prog="myshare_host.cli")
    p.add_argument("message", nargs="?", help="send one message and exit")
    p.add_argument("--email", default="demo@myshare.app")
    p.add_argument("--password", default="password123")
    p.add_argument("--thread", help="continue an existing thread id")
    p.add_argument("-v", "--verbose", action="store_true", help="print raw MCP responses")
    try:
        asyncio.run(main_async(p.parse_args()))
    except (KeyboardInterrupt, EOFError):
        print()


if __name__ == "__main__":
    main()
