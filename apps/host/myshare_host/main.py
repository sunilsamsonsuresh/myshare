"""The MCP HOST service: owns the LLM, the conversation, and user approval.

The browser talks to this service (never to the MCP server directly):

    POST /chat          stream one chat turn as Server-Sent Events
    GET  /threads/{id}  replay a saved conversation (LangGraph checkpointer)
    GET  /mcp/prompts   the MCP server's prompts, for the chat's slash-command menu
    GET  /mcp/inspect   (dev) everything discovered over MCP, plus the raw handshake
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.sse import EventSourceResponse, ServerSentEvent
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from mcp.shared.exceptions import MCPError
from pydantic import BaseModel, Field

from .config import get_settings
from .graph.builder import build_graph
from .mcp_client import needs_approval
from .service import ChatService, TurnRequest

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    # SQLite checkpointer: every graph step is saved under its thread_id.
    async with AsyncSqliteSaver.from_conn_string(settings.host_checkpoint_db) as saver:
        app.state.chat = ChatService(graph=build_graph(saver))
        yield


app = FastAPI(title="MyShare Host", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_bearer = HTTPBearer(auto_error=False)


def user_token(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> str:
    """The browser sends the user's MyShare JWT; the host forwards it over MCP. It never mints its own."""
    if creds is None:
        raise HTTPException(401, "Log in first: missing Bearer token.")
    return creds.credentials


def chat_service(request: Request) -> ChatService:
    return request.app.state.chat


class ChatIn(BaseModel):
    thread_id: str = Field(min_length=1, max_length=100)
    message: str | None = Field(default=None, max_length=4000)
    resume: dict[str, Any] | None = None
    prompt: dict[str, Any] | None = None


@app.post("/chat", response_class=EventSourceResponse)
async def chat(
    body: ChatIn, token: str = Depends(user_token), svc: ChatService = Depends(chat_service)
) -> AsyncIterator[ServerSentEvent]:
    if not (body.message or body.resume or body.prompt):
        raise HTTPException(422, "Send a message, a resume decision, or a prompt.")
    req = TurnRequest(
        thread_id=body.thread_id, message=body.message, resume=body.resume, prompt=body.prompt
    )
    async for ev in svc.run(token, req):
        name = ev.pop("event")
        yield ServerSentEvent(event=name, data=ev)


@app.get("/threads/{thread_id}")
async def thread_history(
    thread_id: str, token: str = Depends(user_token), svc: ChatService = Depends(chat_service)
) -> dict[str, Any]:
    return await _mcp_call(svc.history(token, thread_id))


@app.get("/mcp/prompts")
async def mcp_prompts(
    token: str = Depends(user_token), svc: ChatService = Depends(chat_service)
) -> list[dict[str, Any]]:
    async def go() -> list[dict[str, Any]]:
        async with svc.connect(token) as conn:
            return [p.model_dump(mode="json", exclude_none=True) for p in await conn.list_prompts()]

    return await _mcp_call(go())


def _dump(items: list[Any]) -> list[dict[str, Any]]:
    """MCP objects as wire JSON (camelCase), like the server sent them."""
    return [x.model_dump(mode="json", by_alias=True, exclude_none=True) for x in items]


@app.get("/mcp/inspect")
async def mcp_inspect(
    token: str = Depends(user_token), svc: ChatService = Depends(chat_service)
) -> dict[str, Any]:
    """Dev-only teaching view: what the host learned from the MCP server, and how."""
    if not get_settings().host_dev_endpoints:
        raise HTTPException(404)

    async def go() -> dict[str, Any]:
        async with svc.connect(token) as conn:
            tools = await conn.list_tools()
            return {
                "transport": conn.transport,
                "server_info": conn.init.server_info.model_dump(mode="json", exclude_none=True),
                "protocol_version": conn.init.protocol_version,
                "capabilities": conn.init.capabilities.model_dump(
                    mode="json", by_alias=True, exclude_none=True
                ),
                "instructions": conn.instructions,
                "tools": [
                    {
                        **t.model_dump(mode="json", by_alias=True, exclude_none=True),
                        "requiresApproval": needs_approval(t),
                    }
                    for t in tools
                ],
                "resources": _dump(await conn.list_resources()),
                "resource_templates": _dump(await conn.list_resource_templates()),
                "prompts": _dump(await conn.list_prompts()),
                # The actual JSON-RPC messages exchanged to build this response, initialize included.
                "wire": conn.tap.messages,
            }

    return await _mcp_call(go())


async def _mcp_call(coro: Any) -> Any:
    try:
        return await coro
    except MCPError as exc:
        raise HTTPException(
            401 if "authenticated" in str(exc).lower() or "token" in str(exc).lower() else 502,
            str(exc),
        ) from None
    except (ConnectionError, OSError) as exc:
        raise HTTPException(502, f"Cannot reach the MCP server: {exc}") from None


@app.get("/health")
def health() -> dict[str, str]:
    s = get_settings()
    return {"status": "ok", "mcp_transport": s.mcp_transport, "model": s.model_name}
