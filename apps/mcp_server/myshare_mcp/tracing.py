"""LangSmith tracing for the MCP server (off unless LANGSMITH_TRACING=true).

`trace_tool_calls` is MCP server middleware, like `capture_request_headers` in auth.py.
It wraps every `tools/call` in one LangSmith run. When the caller is our traced host,
the request's `_meta` names the host's run, and this run nests under it, so one chat
turn is one trace: agent -> tool call -> MCP server -> REST API requests.

Calls from other clients (MCP Inspector, Claude Desktop) become traces of their own.
The privacy filter is the same as the host's: see myshare_shared/tracing.py.
"""

from __future__ import annotations

from typing import Any

import langsmith
from mcp.server.context import CallNext, HandlerResult, ServerRequestContext
from pydantic import BaseModel

from myshare_shared.tracing import parent_from_meta, tracing_enabled


async def trace_tool_calls(
    ctx: ServerRequestContext[Any, Any], call_next: CallNext
) -> HandlerResult:
    """MCP server middleware: one LangSmith run per `tools/call` (a pass-through when tracing is off)."""
    if ctx.method != "tools/call" or not tracing_enabled():
        return await call_next(ctx)
    params = ctx.params or {}
    name = str(params.get("name", "unknown"))
    with (
        langsmith.tracing_context(parent=parent_from_meta(ctx.meta)),
        langsmith.trace(
            f"MCP server: {name}",
            run_type="chain",
            inputs={"tool": name, "arguments": params.get("arguments") or {}},
        ) as run,
    ):
        result = await call_next(ctx)
        outputs = (
            result.model_dump(mode="json", exclude_none=True)
            if isinstance(result, BaseModel)
            else {"result": result}
        )
        run.end(outputs=outputs)
        return result
