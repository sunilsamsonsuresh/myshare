"""Where does the end user's token come from? It depends on the transport.

MCP itself doesn't define "who is the user"; that's the transport's job:

* Streamable HTTP: every JSON-RPC message arrives as an HTTP POST, so it can carry
  an `Authorization: Bearer <jwt>` header. The host sets that header per user.
  One running server can safely serve many users at once.

* stdio: the server is a child process of one host, talking over stdin/stdout.
  There are no headers. The host passes the token when it launches the process
  (env var MYSHARE_USER_TOKEN), so one stdio process = one user.

How we read the header: `capture_request_headers` is MCP server middleware. It
wraps every inbound MCP message (tools/call, resources/read, prompts/get...),
and stashes that message's HTTP headers in a ContextVar for the duration of the
handler. (Tools could use `ctx.headers` directly, but in SDK v2 static resources
like `myshare://me/summary` can't receive a Context, so middleware is the one
mechanism that works for all three primitives.)

What we NEVER do: fall back to a shared "service account" token. If this server
held an admin credential, every user's request would run with admin rights, the
API's per-user authorization ("only members can see this group") would be
bypassed, and a prompt-injected LLM could read or modify anyone's data. See
docs/MCP_EXPLAINED.md section 6.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from contextvars import ContextVar
from typing import Any

from mcp.server.context import CallNext, HandlerResult, ServerRequestContext
from mcp.server.mcpserver.exceptions import ToolError

TOKEN_ENV = "MYSHARE_USER_TOKEN"

# None = "this message did not arrive over HTTP" (stdio or in-memory).
_request_headers: ContextVar[Mapping[str, str] | None] = ContextVar(
    "mcp_request_headers", default=None
)


async def capture_request_headers(
    ctx: ServerRequestContext[Any, Any], call_next: CallNext
) -> HandlerResult:
    """MCP server middleware: expose the current HTTP request's headers to handlers."""
    # With Streamable HTTP, ctx.request is the Starlette Request for this POST.
    headers = getattr(ctx.request, "headers", None)
    reset = _request_headers.set(headers)
    try:
        return await call_next(ctx)
    finally:
        _request_headers.reset(reset)


class NotAuthenticated(ToolError):
    pass


def user_token() -> str:
    headers = _request_headers.get()
    if headers is not None:
        scheme, _, token = headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            # Deliberately no fallback to the env var here: an HTTP caller without
            # a token is anonymous, full stop.
            raise NotAuthenticated(
                "Not authenticated: send the user's MyShare JWT as 'Authorization: Bearer <token>' "
                "on every MCP HTTP request."
            )
        return token.strip()

    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        raise NotAuthenticated(
            f"Not authenticated: in stdio mode, launch the server with the user's MyShare JWT in {TOKEN_ENV}."
        )
    return token
