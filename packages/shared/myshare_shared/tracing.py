"""LangSmith tracing for MyShare: one on/off switch and one privacy filter, shared by
the host (the LangGraph agent) and the MCP server.

Turn it on in .env (both processes read the same variables):

    LANGSMITH_TRACING=true
    LANGSMITH_API_KEY=lsv2_...
    LANGSMITH_PROJECT=myshare
    LANGSMITH_ENDPOINT=https://...      # your account's region

With LANGSMITH_TRACING=false (or no key), nothing is sent and the app behaves exactly
the same.

What a trace contains by default: which steps ran, in what order, how long each took,
token counts, tool names, argument NAMES, ids and errors. Text and values (chat
messages, expense descriptions, amounts, people's names and emails, tool results)
are replaced by "[hidden]" before anything leaves this machine.

MYSHARE_TRACE_CONTENT=true records them in full. Use it only with synthetic data
(e.g. `make seed`) while debugging a prompt or a tool.
"""

from __future__ import annotations

import dataclasses
import logging
import os
from collections.abc import Mapping
from typing import Any

import langsmith
from langsmith.run_trees import RunTree
from langsmith.utils import tracing_is_enabled

log = logging.getLogger("myshare.tracing")

HIDDEN = "[hidden]"
CONTENT_ENV = "MYSHARE_TRACE_CONTENT"

# Values under these keys describe the SHAPE of a step, not the user's data, so they stay.
_KEEP = {
    "type",
    "role",
    "id",
    "tool",
    "tool_call_id",
    "status",
    "phase",
    "is_error",
    "model",
    "model_name",
    "stop_reason",
    "finish_reason",
}
# Every number inside these is a token count.
_COUNTS = {"usage_metadata", "usage", "token_usage"}
# In a dict with one of these "type"s, "name" is a tool's name (keep), not a person's (hide).
_TOOL_TYPES = {"tool", "tool_call", "tool_call_chunk", "tool_use", "server_tool_use"}
_MAX_DEPTH = 25

_configured = False


def tracing_enabled() -> bool:
    return bool(tracing_is_enabled())


def content_enabled() -> bool:
    return os.environ.get(CONTENT_ENV, "").strip().lower() in ("1", "true", "yes")


def configure_tracing(service: str) -> None:
    """Install the privacy filter on the LangSmith client every trace goes through.

    Call it once at startup, before the first traced call. Safe to call again, and a
    no-op when tracing is off. LangChain/LangGraph runs and our own `langsmith.trace`
    runs all use this global client, so one filter covers everything.
    """
    global _configured
    if _configured or not tracing_enabled():
        return
    _configured = True
    project = os.environ.get("LANGSMITH_PROJECT", "default")
    if content_enabled():
        log.warning(
            "LangSmith tracing ON for %s -> project %r, INCLUDING message and tool content "
            "(%s=true). Use synthetic data only.",
            service,
            project,
            CONTENT_ENV,
        )
        return
    langsmith.configure(client=langsmith.Client(hide_inputs=redact, hide_outputs=redact))
    log.info(
        "LangSmith tracing ON for %s -> project %r (content hidden; %s=true to include it)",
        service,
        project,
        CONTENT_ENV,
    )


def redact(payload: Any) -> dict[str, Any]:
    """Keep a run's structure, replace its text and values with "[hidden]".

    LangSmith calls this on every run's inputs and outputs before upload. It must never
    raise (that would drop the run) and never fall back to the raw payload.
    """
    try:
        masked = _mask(_plain(payload, 0), None, counts=False)
    except Exception:
        return {"redacted": HIDDEN}
    return masked if isinstance(masked, dict) else {"value": masked}


def _plain(obj: Any, depth: int) -> Any:
    """Live objects (LangChain messages, MCP results, dataclasses) -> plain JSON-like data."""
    if depth > _MAX_DEPTH:
        return HIDDEN
    if obj is None or isinstance(obj, str | int | float | bool):
        return obj
    if isinstance(obj, Mapping):
        return {str(k): _plain(v, depth + 1) for k, v in obj.items()}
    if isinstance(obj, list | tuple | set | frozenset):
        return [_plain(v, depth + 1) for v in obj]
    if hasattr(obj, "model_dump"):  # pydantic: LangChain messages, MCP types
        try:
            return _plain(obj.model_dump(mode="json"), depth + 1)
        except Exception:
            return f"<{type(obj).__name__}>"
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        # Field by field, not dataclasses.asdict(): asdict deep-copies live objects
        # (an MCP session, a model client), which can fail or be slow.
        return {f.name: _plain(getattr(obj, f.name), depth + 1) for f in dataclasses.fields(obj)}
    return f"<{type(obj).__name__}>"


def _mask(value: Any, key: str | None, counts: bool) -> Any:
    if isinstance(value, dict):
        tool_name_ok = value.get("type") in _TOOL_TYPES
        return {
            k: v
            if k == "name" and tool_name_ok and isinstance(v, str)
            else _mask(v, k, counts or k in _COUNTS)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_mask(v, key, counts) for v in value]
    if value is None or isinstance(value, bool):
        return value
    if key in _KEEP and isinstance(value, str | int):
        return value
    if counts and isinstance(value, int | float):
        return value
    return HIDDEN


# ---- linking the MCP server's runs under the host's run (two processes, one trace)
#
# The host puts its current run's id in the `_meta` of each `tools/call` request; the
# server makes its run a child of that id. Only the `langsmith-trace` header is sent,
# not the `baggage` one, so a client can't choose which project the server writes to.
_META_KEY = "langsmith-trace"


def trace_meta(run: RunTree) -> dict[str, Any] | None:
    """`_meta` for an outgoing MCP request: who the parent run is (None when tracing is off)."""
    if not tracing_enabled():
        return None
    return {_META_KEY: run.to_headers()[_META_KEY]}


def parent_from_meta(meta: Mapping[str, Any] | None) -> dict[str, str] | None:
    """The parent-run header from an incoming MCP request's `_meta`, if a traced host sent one."""
    value = (meta or {}).get(_META_KEY)
    return {_META_KEY: value} if isinstance(value, str) and value else None
