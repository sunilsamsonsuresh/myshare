"""Run the REAL host on :8002 with a tiny keyword-driven stand-in for the LLM.

    uv run --env-file .env python scripts/fake_host.py

DEV/DEMO AID ONLY. Everything except the language model is real: the MCP client,
the LangGraph graph, the approval interrupt, SSE streaming, the MCP server and the
API. Useful for working on the chat UI (or demoing MCP) without an Anthropic key.
The "model" just maps keywords to tool calls, so it only understands a few phrases:

    "who owes me"            -> get_balances
    "add ... cab"            -> add_expense (Goa Trip, ₹1,800, equal)  [approval]
    "settle" / "simplest"    -> get_simplified_debts (Goa Trip)
    "delete the last"        -> list_expenses, then delete_expense     [approval]
    "last ... expenses"      -> list_expenses
    "split ₹X <what> with A and B in <group>"
                             -> resolve_person(A), resolve_person(B), list_groups,
                                then add_expense with their ids               [approval]
"""

from __future__ import annotations

import functools
import json
import re
import sys
import uuid
from pathlib import Path
from typing import Any

import uvicorn
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)
from langchain_core.messages.tool import tool_call_chunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from myshare_host import main as host_main  # noqa: E402

GOA = 1  # the seeded "Goa Trip" group id


def _call(name: str, args: dict[str, Any]) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {"name": name, "args": args, "id": f"demo_{uuid.uuid4().hex[:8]}", "type": "tool_call"}
        ],
    )


def _calls(*specs: tuple[str, dict[str, Any]]) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {"name": n, "args": a, "id": f"demo_{uuid.uuid4().hex[:8]}", "type": "tool_call"}
            for n, a in specs
        ],
    )


def _result_json(msg: ToolMessage) -> dict[str, Any]:
    m = re.search(r"\n(\{.*\})\n</tool_result>", str(msg.content), re.S)
    return json.loads(m.group(1)) if m else {}


class KeywordModel(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "keyword-demo"

    def bind_tools(self, tools: Any, **kwargs: Any) -> KeywordModel:  # type: ignore[override]
        return self

    def _plan_split(self, messages: list[BaseMessage], text: str) -> AIMessage:
        """Second step of "split ₹X ... with A and B in G": ids are known, propose add_expense."""
        tool_msgs = [m for m in messages if isinstance(m, ToolMessage)][-3:]
        people = [_result_json(m) for m in tool_msgs if m.name == "resolve_person"]
        if any(p.get("status") != "unique" for p in people):
            return AIMessage(
                content="I found more than one match (or none) for someone you mentioned. Who did you mean?"
            )
        groups = next((_result_json(m)["groups"] for m in tool_msgs if m.name == "list_groups"), [])
        group = next((g for g in groups if g["name"].lower() in text), None)
        if group is None:
            return AIMessage(content="Which group should this go in?")
        me = re.search(r'"user":\s*\{\s*"id":\s*(\d+)', str(messages[0].content))
        amount = re.search(r"(?:₹|rs\.?\s*|inr\s*)([\d,]+(?:\.\d+)?)", text)
        what = re.search(r"[\d,] (\w+)", text)
        participants = [{"user_id": int(me.group(1))}] if me else []
        participants += [{"user_id": p["matches"][0]["id"]} for p in people]
        return _call(
            "add_expense",
            {
                "description": (what.group(1) if what else "expense").capitalize(),
                "amount": amount.group(1).replace(",", "") if amount else "0",
                "group_id": group["id"],
                "split": {"type": "equal", "participants": participants},
            },
        )

    def _decide(self, messages: list[BaseMessage]) -> AIMessage:
        last = messages[-1]
        human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
        text = (human.text if human else "").lower()
        if (
            isinstance(last, ToolMessage)
            and last.name in ("resolve_person", "list_groups")
            and text.startswith("split")
        ):
            return self._plan_split(messages, text)
        if isinstance(last, ToolMessage):
            if last.name == "list_expenses" and "delete" in text:
                items = _result_json(last).get("expenses", [])
                if items:
                    e = items[0]
                    return _call("delete_expense", {"expense_id": e["id"]})
            if "REJECTED" in str(last.content):
                return AIMessage(content="Okay, I didn't change anything.")
            first = (
                str(last.content).split("\n")[1] if "\n" in str(last.content) else str(last.content)
            )
            return AIMessage(
                content=f"{first}\n\n_(offline demo model: this summary is the tool's own text)_"
            )
        if text.startswith("split"):
            names = re.findall(r"with ([a-z]+)(?: and ([a-z]+))?", text)
            people = [n for n in (names[0] if names else ()) if n]
            return _calls(*[("resolve_person", {"name": n}) for n in people], ("list_groups", {}))
        if "owe" in text:
            return _call("get_balances", {})
        if "cab" in text or text.startswith("add"):
            return _call(
                "add_expense",
                {
                    "description": "Cab",
                    "amount": "1800",
                    "group_id": GOA,
                    "category": "transport",
                    "split": {"type": "equal"},
                },
            )
        if "settle" in text or "simplest" in text:
            return _call("get_simplified_debts", {"group_id": GOA})
        if "delete" in text:
            return _call("list_expenses", {"limit": 1})
        if "expense" in text:
            return _call("list_expenses", {"limit": 5})
        return AIMessage(
            content="I'm the **offline demo model**. Try: *Who owes me money?*, *Add ₹1,800 for cab to Goa Trip*, "
            "*What's the simplest way to settle Goa Trip?* or *Delete the last expense*."
        )

    def _generate(
        self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None, **kw: Any
    ) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self._decide(messages))])

    def _stream(
        self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None, **kw: Any
    ):
        msg = self._decide(messages)
        for word in str(msg.content).split(" ") if msg.content else []:
            chunk = ChatGenerationChunk(message=AIMessageChunk(content=word + " "))
            if run_manager:
                run_manager.on_llm_new_token(chunk.text, chunk=chunk)
            yield chunk
        if msg.tool_calls:
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content="",
                    tool_call_chunks=[
                        tool_call_chunk(
                            name=c["name"], args=json.dumps(c["args"]), id=c["id"], index=i
                        )
                        for i, c in enumerate(msg.tool_calls)
                    ],
                )
            )


if __name__ == "__main__":
    # The host's lifespan builds ChatService(...); make it use the keyword model instead of Claude.
    host_main.ChatService = functools.partial(host_main.ChatService, llm_factory=KeywordModel)  # type: ignore[misc]
    print("Fake host (keyword model, NOT an LLM) on http://localhost:8002", file=sys.stderr)
    uvicorn.run(host_main.app, port=8002)
