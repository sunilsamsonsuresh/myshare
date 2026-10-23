"""Graph nodes. Each one is a small async function: (state, runtime) -> state update.

    load_context ──► agent ──► (no tool calls) ──► END
                       ▲   │
                       │   ├─► (only read-only tools) ──────────────────► tools ─┐
                       │   └─► (any write tool) ─► prepare_approval ─► approval ─► tools ─┤
                       └──────────────────────────────────────────────────────────────────┘

Nodes talk to the UI through LangGraph's custom stream (runtime.stream_writer):
the FastAPI layer turns those dicts into SSE events.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langgraph.graph import END
from langgraph.runtime import Runtime
from langgraph.types import interrupt

from ..mcp_client import frame_for_llm, needs_approval, result_text, supports_dry_run
from .prompts import build_system_prompt
from .state import AgentState, Decision, HostContext, PendingAction

ME_RESOURCE = "myshare://me/summary"


def _last_ai(state: AgentState) -> AIMessage:
    msg = state["messages"][-1]
    assert isinstance(msg, AIMessage), "expected the last message to come from the agent"
    return msg


def _first_line(text: str) -> str:
    return text.strip().split("\n", 1)[0]


# --------------------------------------------------------------------------- load_context
async def load_context(state: AgentState, runtime: Runtime[HostContext]) -> dict[str, Any]:
    """Read an MCP RESOURCE and put it in the system prompt.

    This is application-controlled context: the host (not the model) decides to read
    myshare://me/summary at the start of every turn. The model then knows who "me" is,
    and the user's current balances, without spending a tool call.
    """
    ctx = runtime.context
    text = await ctx.conn.read_text_resource(ME_RESOURCE)
    req, resp = ctx.conn.tap.last_exchange("resources/read")
    runtime.stream_writer(
        {"event": "resource_read", "uri": ME_RESOURCE, "request": req, "response": resp}
    )
    gated = [name for name, tool in ctx.tools.items() if needs_approval(tool)]
    return {"user_context": text, "gated_tools": gated}


# --------------------------------------------------------------------------- agent
async def agent(state: AgentState, runtime: Runtime[HostContext]) -> dict[str, Any]:
    """The LLM call. Tokens stream to the UI via LangGraph's "messages" stream mode."""
    ctx = runtime.context
    system = SystemMessage(
        build_system_prompt(state.get("user_context", ""), ctx.conn.instructions)
    )
    response = await ctx.llm.ainvoke([system, *state["messages"]])
    return {"messages": [response]}


def route_after_agent(state: AgentState) -> str:
    calls = _last_ai(state).tool_calls
    if not calls:
        return END
    gated = set(state.get("gated_tools", []))
    return "prepare_approval" if any(c["name"] in gated for c in calls) else "tools"


# --------------------------------------------------------------------------- approval
async def prepare_approval(state: AgentState, runtime: Runtime[HostContext]) -> dict[str, Any]:
    """Dry-run each write so the approval card shows exactly what would happen.

    If the dry run fails (e.g. "Rahul isn't in this group"), we skip the approval and
    hand the error straight back to the model to fix. The user is never asked to
    approve something that can't succeed.
    """
    ctx = runtime.context
    gated = set(state.get("gated_tools", []))
    pending: list[PendingAction] = []
    decisions: dict[str, Decision] = {}

    for call in _last_ai(state).tool_calls:
        if call["name"] not in gated:
            continue
        tool = ctx.tools.get(call["name"])
        call_id = call["id"] or ""
        details: dict[str, Any] | None = None
        if tool is not None and supports_dry_run(tool):
            args = {**call["args"], "dry_run": True}
            runtime.stream_writer(
                {
                    "event": "tool_call_started",
                    "id": call_id,
                    "tool": call["name"],
                    "args": args,
                    "phase": "preview",
                }
            )
            result = await ctx.conn.call_tool(call["name"], args)
            req, resp = ctx.conn.tap.last_exchange("tools/call")
            runtime.stream_writer(
                {
                    "event": "tool_call_result",
                    "id": call_id,
                    "tool": call["name"],
                    "phase": "preview",
                    "status": "error" if result.is_error else "ok",
                    "summary": _first_line(result_text(result)),
                    "request": req,
                    "response": resp,
                }
            )
            if result.is_error:
                decisions[call_id] = {
                    "action": "invalid",
                    "message": frame_for_llm(call["name"], result),
                }
                continue
            preview = _first_line(result_text(result)).replace(
                "PREVIEW (nothing saved): would ", ""
            )
            details = result.structured_content
        else:
            preview = f"{call['name']}({json.dumps(call['args'], ensure_ascii=False)})"
        pending.append(
            {
                "tool_call_id": call_id,
                "tool": call["name"],
                "title": (tool.title if tool and tool.title else call["name"]),
                "args": call["args"],
                "preview": preview[:1].upper() + preview[1:],
                "details": details,
                "destructive": bool(
                    tool and tool.annotations and tool.annotations.destructive_hint
                ),
            }
        )
    return {"pending": pending, "decisions": decisions}


def route_after_prepare(state: AgentState) -> str:
    return "approval" if state.get("pending") else "tools"


def approval(state: AgentState) -> dict[str, Any]:
    """Human-in-the-loop gate: pause the graph until the user decides.

    `interrupt()` saves the graph state in the checkpointer and stops the run; the
    UI gets an `approval_required` event. When the user clicks Approve/Reject, the
    host resumes the SAME thread with `Command(resume={...})`, and `interrupt()`
    returns that value right here. (On resume LangGraph re-runs this node from the
    top, which is why the slow dry runs live in prepare_approval, not here.)

    Resume value: {"decisions": {tool_call_id: {"action": "approve"|"reject"|"edit",
                                                "feedback": "..."}}}
             or   {"action": "approve"} to apply one decision to every pending action.
    """
    pending = state.get("pending", [])
    answer = interrupt({"type": "approval", "actions": pending})
    answer = answer if isinstance(answer, dict) else {}
    decisions: dict[str, Decision] = dict(state.get("decisions", {}))
    per_call = answer.get("decisions", {})
    for p in pending:
        d = per_call.get(p["tool_call_id"]) or (
            {"action": answer["action"]} if "action" in answer else None
        )
        if d is None or d.get("action") not in ("approve", "reject", "edit"):
            d = {"action": "reject", "feedback": "No decision was received."}
        decisions[p["tool_call_id"]] = d  # type: ignore[assignment]
    return {"decisions": decisions, "pending": []}


# --------------------------------------------------------------------------- tools
async def tools(state: AgentState, runtime: Runtime[HostContext]) -> dict[str, Any]:
    """Execute the model's tool calls over MCP (`tools/call`) and return ToolMessages."""
    ctx = runtime.context
    emit = runtime.stream_writer
    decisions = state.get("decisions", {})
    gated = set(state.get("gated_tools", []))
    out: list[ToolMessage] = []

    for call in _last_ai(state).tool_calls:
        call_id, name, args = call["id"] or "", call["name"], call["args"]
        d = decisions.get(call_id)

        if d is not None and d["action"] != "approve":
            if d["action"] == "invalid":
                text, status = d.get("message", "Invalid request."), "error"
            elif d["action"] == "edit":
                text = (
                    "The user did NOT approve this action and asked for changes: "
                    f"{d.get('feedback') or '(no details)'}. Propose a corrected action; it will need approval again."
                )
                status = "changes_requested"
            else:
                reason = f" Reason: {d.get('feedback')}" if d.get("feedback") else ""
                text = f"The user REJECTED this action; nothing was changed.{reason} Do not retry unless they ask."
                status = "rejected"
            if d["action"] != "invalid":  # invalid ones were already shown as a failed preview
                emit(
                    {
                        "event": "tool_call_result",
                        "id": call_id,
                        "tool": name,
                        "phase": "call",
                        "status": status,
                        "summary": text,
                    }
                )
            out.append(ToolMessage(text, tool_call_id=call_id, name=name, status="error"))
            continue

        emit(
            {
                "event": "tool_call_started",
                "id": call_id,
                "tool": name,
                "args": args,
                "phase": "call",
            }
        )
        try:
            result = await ctx.conn.call_tool(name, args)
        except Exception as exc:  # transport/protocol failure (not a tool error)
            text = f"The tool could not be called: {exc}"
            emit(
                {
                    "event": "tool_call_result",
                    "id": call_id,
                    "tool": name,
                    "phase": "call",
                    "status": "error",
                    "summary": text,
                }
            )
            out.append(ToolMessage(text, tool_call_id=call_id, name=name, status="error"))
            continue

        req, resp = ctx.conn.tap.last_exchange("tools/call")
        emit(
            {
                "event": "tool_call_result",
                "id": call_id,
                "tool": name,
                "phase": "call",
                "status": "error" if result.is_error else "ok",
                "summary": _first_line(result_text(result)),
                "structured": result.structured_content,
                "request": req,
                "response": resp,
                "is_write": name in gated,
            }
        )
        out.append(
            ToolMessage(
                frame_for_llm(name, result),
                tool_call_id=call_id,
                name=name,
                status="error" if result.is_error else "success",
            )
        )
    return {"messages": out, "decisions": {}}
