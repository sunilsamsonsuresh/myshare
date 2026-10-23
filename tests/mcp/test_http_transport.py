"""Streamable HTTP end to end: a real uvicorn server, a real MCP client, per-user headers.

Proves the auth story: the SAME running MCP server returns different data for
different users, because each request carries that user's own Bearer token.
"""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator

import httpx
import httpx2
import pytest
import uvicorn
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from myshare_mcp import api_client
from myshare_mcp.server import mcp
from tests.mcp.test_mcp_server import text

pytestmark = pytest.mark.anyio


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def mcp_url(api_app, monkeypatch) -> Iterator[str]:
    api_client.use_transport(httpx.ASGITransport(app=api_app))
    monkeypatch.setenv("MYSHARE_API_URL", "http://api.test")
    monkeypatch.delenv("MYSHARE_USER_TOKEN", raising=False)  # HTTP mode must never use it
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(mcp.streamable_http_app(), host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/mcp"
    server.should_exit = True
    thread.join(timeout=5)
    api_client.use_transport(None)


def connect(url: str, token: str | None) -> Client:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    # The SDK's HTTP client is httpx2; headers set here go on EVERY MCP POST.
    return Client(
        streamable_http_client(url, http_client=httpx2.AsyncClient(headers=headers, timeout=10))
    )


async def test_each_user_sees_their_own_data(client, people, trip, mcp_url):
    async with connect(mcp_url, people["me"].token) as me:
        r = await me.call_tool("list_groups", {})
        assert [g["name"] for g in r.structured_content["groups"]] == ["Goa Trip"]

    async with connect(mcp_url, people["mallory"].token) as mallory:
        r = await mallory.call_tool("list_groups", {})
        assert r.structured_content["groups"] == []
        r = await mallory.call_tool("get_group_details", {"group_id": trip})
        assert r.is_error and "not a member" in text(r)


async def test_no_token_no_access(client, people, trip, mcp_url):
    async with connect(mcp_url, None) as anon:
        r = await anon.call_tool("list_groups", {})
        assert r.is_error and "Not authenticated" in text(r)
