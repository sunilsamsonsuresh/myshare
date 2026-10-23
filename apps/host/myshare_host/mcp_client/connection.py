"""The host's MCP client, built directly on the SDK's `ClientSession`.

The full life of one connection, step by step:

    1. TRANSPORT   open a pipe to the server.
                   http : Streamable HTTP. Every JSON-RPC message is an HTTP POST to
                          MCP_SERVER_URL, carrying `Authorization: Bearer <user JWT>`.
                   stdio: launch the server as a subprocess and talk over its
                          stdin/stdout. The user's JWT goes in its environment.
    2. SESSION     wrap the transport's (read, write) streams in a `ClientSession`,
                   which handles JSON-RPC ids, request/response matching, timeouts.
    3. INITIALIZE  `session.initialize()` sends `initialize` (our protocol version,
                   capabilities, client name) and receives the server's version,
                   capabilities (tools? resources? prompts?) and instructions.
                   Then the client sends `notifications/initialized`.
    4. USE         tools/list, tools/call, resources/list, resources/read, prompts/list,
                   prompts/get: plain request/response pairs.
    5. CLOSE       exit the context managers. For HTTP the SDK sends a DELETE to end
                   the session; for stdio the subprocess is terminated.

The SDK also offers a higher-level `mcp.Client` that does all of this for you
(and, by default, uses the newer 2026-07-28 `server/discover` handshake). We
use `ClientSession` + `initialize()` deliberately so every step above is
visible in this file.

Connection lifetime: one connection per chat request, opened with that user's
token. That's the simplest correct way to keep users separate. (A busier host
would pool sessions per user; see the exercises in docs/MCP_EXPLAINED.md.)
"""

from __future__ import annotations

import shlex
import sys
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import httpx2
from mcp import ClientSession
from mcp.client._transport import TransportStreams
from mcp.client.stdio import StdioServerParameters, get_default_environment, stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import (
    CallToolResult,
    GetPromptResult,
    Implementation,
    InitializeResult,
    PaginatedRequestParams,
    Prompt,
    ReadResourceResult,
    Resource,
    ResourceTemplate,
    Tool,
)

from ..config import Settings, get_settings
from .wire import WireTap

CLIENT_INFO = Implementation(name="myshare-host", version="0.1.0")


@dataclass
class MCPConnection:
    """A live, initialized MCP session for ONE user, plus small conveniences."""

    session: ClientSession
    init: InitializeResult
    tap: WireTap
    transport: str
    _tools: list[Tool] | None = field(default=None, repr=False)
    _resource_text: dict[str, str] = field(default_factory=dict, repr=False)

    # ---- what the server told us during `initialize`
    @property
    def server_name(self) -> str:
        return self.init.server_info.name

    @property
    def instructions(self) -> str | None:
        return self.init.instructions

    # ---- tools (model-controlled)
    async def list_tools(self) -> list[Tool]:
        """`tools/list`, following pagination cursors, cached for this connection."""
        if self._tools is None:
            tools: list[Tool] = []
            cursor: str | None = None
            while True:
                page = await self.session.list_tools(
                    params=PaginatedRequestParams(cursor=cursor) if cursor else None
                )
                tools.extend(page.tools)
                cursor = page.next_cursor
                if not cursor:
                    break
            self._tools = tools
        return self._tools

    async def get_tool(self, name: str) -> Tool | None:
        return next((t for t in await self.list_tools() if t.name == name), None)

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> CallToolResult:
        """`tools/call`. A tool *failure* comes back as a result with is_error=True (not an exception)."""
        return await self.session.call_tool(name, arguments)

    # ---- resources (application-controlled)
    async def list_resources(self) -> list[Resource]:
        return (await self.session.list_resources()).resources

    async def list_resource_templates(self) -> list[ResourceTemplate]:
        return (await self.session.list_resource_templates()).resource_templates

    async def read_resource(self, uri: str) -> ReadResourceResult:
        return await self.session.read_resource(uri)

    async def read_text_resource(self, uri: str) -> str:
        """Text of a resource. Cached for this connection, which lives for one chat turn,
        so the identity check and the load_context node share a single resources/read."""
        if uri not in self._resource_text:
            contents = (await self.read_resource(uri)).contents
            self._resource_text[uri] = "\n".join(getattr(c, "text", "") for c in contents)
        return self._resource_text[uri]

    # ---- prompts (user-controlled)
    async def list_prompts(self) -> list[Prompt]:
        return (await self.session.list_prompts()).prompts

    async def get_prompt(
        self, name: str, arguments: dict[str, str] | None = None
    ) -> GetPromptResult:
        return await self.session.get_prompt(name, arguments or {})


def _http_transport(
    settings: Settings, token: str
) -> AbstractAsyncContextManager[TransportStreams]:
    # Per-user auth for Streamable HTTP: a header on every POST. The SDK uses httpx2.
    http = httpx2.AsyncClient(
        headers={"Authorization": f"Bearer {token}"},
        timeout=httpx2.Timeout(30.0, read=120.0),
    )
    return streamable_http_client(settings.mcp_server_url, http_client=http)


def _stdio_transport(
    settings: Settings, token: str
) -> AbstractAsyncContextManager[TransportStreams]:
    argv = shlex.split(settings.mcp_stdio_command)
    if argv and argv[0] == "python":
        argv[0] = sys.executable  # same virtualenv as the host
    params = StdioServerParameters(
        command=argv[0],
        args=argv[1:],
        # stdio has no headers: identity travels in the subprocess environment.
        # get_default_environment() passes only a safe allow-list (PATH, HOME...), so the
        # host's own secrets (like ANTHROPIC_API_KEY) are NOT leaked to the server.
        env={
            **get_default_environment(),
            "MYSHARE_USER_TOKEN": token,
            "MYSHARE_API_URL": settings.myshare_api_url,
        },
    )
    return stdio_client(params)


@asynccontextmanager
async def connect_mcp(
    token: str,
    *,
    settings: Settings | None = None,
    transport: AbstractAsyncContextManager[TransportStreams] | None = None,
) -> AsyncIterator[MCPConnection]:
    """Open, initialize and (on exit) close an MCP connection acting as the user with `token`.

    `transport` overrides the configured one (tests pass an in-memory transport).
    """
    settings = settings or get_settings()
    mode = "custom" if transport is not None else settings.mcp_transport
    if transport is None:
        transport = (
            _http_transport(settings, token)
            if mode == "http"
            else _stdio_transport(settings, token)
        )

    tap = WireTap(debug=settings.mcp_debug_wire, label=mode)
    async with AsyncExitStack() as stack:
        # 1. transport -> raw (read, write) streams of JSON-RPC messages
        read, write = await stack.enter_async_context(transport)
        # (wire tap: record every message that crosses the streams)
        read, write = tap.wrap(read, write)
        # 2. session over the streams
        session = await stack.enter_async_context(
            ClientSession(read, write, client_info=CLIENT_INFO)
        )
        # 3. the handshake
        init = await session.initialize()
        # 4. hand the live connection to the caller; 5. closes when the `async with` ends
        yield MCPConnection(session=session, init=init, tap=tap, transport=mode)
