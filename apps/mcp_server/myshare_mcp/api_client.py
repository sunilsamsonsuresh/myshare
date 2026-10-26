"""A small async client for the MyShare REST API.

The MCP server talks to the API over HTTP, exactly like any third-party
integration would. It never imports the API's database layer. This keeps one
source of truth for business rules and authorization (the API), and makes the
MCP server a thin, replaceable adapter.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
import langsmith
from mcp.server.mcpserver.exceptions import ToolError

DEFAULT_API_URL = "http://localhost:8000"

# Tests swap this for an in-process ASGI transport (no network needed).
_transport: httpx.AsyncBaseTransport | None = None


def use_transport(transport: httpx.AsyncBaseTransport | None) -> None:
    global _transport
    _transport = transport


class APIError(ToolError):
    """An API error, re-raised as a ToolError so the LLM sees the message and can self-correct.

    A ToolError becomes `CallToolResult(is_error=True)`, which the model reads as a normal
    tool result. Any other exception would become an opaque protocol error.
    """

    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(detail)


def _detail(resp: httpx.Response) -> str:
    try:
        body = resp.json()
    except ValueError:
        return resp.text or resp.reason_phrase
    detail = body.get("detail", body) if isinstance(body, dict) else body
    if isinstance(detail, list):  # FastAPI/Pydantic validation errors -> one readable line each
        return "; ".join(
            f"{'.'.join(str(p) for p in d.get('loc', [])[1:])}: {d.get('msg')}" for d in detail
        )
    return str(detail)


class MyShareAPI:
    def __init__(self, token: str, base_url: str | None = None):
        self._client = httpx.AsyncClient(
            base_url=base_url or os.environ.get("MYSHARE_API_URL", DEFAULT_API_URL),
            # The END USER's token, forwarded as-is. The API decides what this user may do.
            headers={"Authorization": f"Bearer {token}"},
            timeout=15.0,
            transport=_transport,
        )

    async def __aenter__(self) -> MyShareAPI:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._client.aclose()

    async def request(self, method: str, path: str, **kw: Any) -> Any:
        # Drop None query params so optional filters don't become "?x=None".
        if "params" in kw:
            kw["params"] = {k: v for k, v in kw["params"].items() if v is not None}
        # One LangSmith run per REST call made inside a traced tool call. Calls outside one
        # (e.g. resource reads) would each become a stray one-step trace, so they aren't
        # traced. The bearer token is never an input: it lives in the client's default headers.
        if langsmith.get_current_run_tree() is None:
            return await self._send(method, path, **kw)
        with langsmith.trace(
            f"{method} {path}",
            run_type="tool",
            inputs={"params": kw.get("params"), "body": kw.get("json")},
        ) as run:
            data = await self._send(method, path, **kw)
            run.end(outputs={"response": data})
            return data

    async def _send(self, method: str, path: str, **kw: Any) -> Any:
        try:
            resp = await self._client.request(method, path, **kw)
        except httpx.HTTPError as exc:
            raise ToolError(
                f"The MyShare API is unreachable ({exc.__class__.__name__}). Try again shortly."
            ) from exc
        if resp.status_code == 401:
            raise APIError(
                401,
                "The user's session has expired or the token is invalid. Ask them to log in again.",
            )
        if resp.status_code >= 400:
            raise APIError(resp.status_code, _detail(resp))
        return resp.json()

    async def get(self, path: str, **params: Any) -> Any:
        return await self.request("GET", path, params=params)

    async def post(self, path: str, body: dict[str, Any], *, dry_run: bool = False) -> Any:
        return await self.request("POST", path, json=body, params={"dry_run": dry_run or None})

    async def patch(self, path: str, body: dict[str, Any], *, dry_run: bool = False) -> Any:
        return await self.request("PATCH", path, json=body, params={"dry_run": dry_run or None})

    async def delete(self, path: str, *, dry_run: bool = False) -> Any:
        return await self.request("DELETE", path, params={"dry_run": dry_run or None})
