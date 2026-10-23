"""Fixtures shared by the host tests."""

from __future__ import annotations

import httpx
import pytest
from langgraph.checkpoint.memory import InMemorySaver

from myshare_mcp import api_client


@pytest.fixture
def wire(api_app, monkeypatch):
    """MCP server -> in-memory API. Returns a function selecting the acting user."""
    api_client.use_transport(httpx.ASGITransport(app=api_app))
    monkeypatch.setenv("MYSHARE_API_URL", "http://api.test")
    yield lambda person: monkeypatch.setenv("MYSHARE_USER_TOKEN", person.token)
    api_client.use_transport(None)


@pytest.fixture
def saver():
    return InMemorySaver()
