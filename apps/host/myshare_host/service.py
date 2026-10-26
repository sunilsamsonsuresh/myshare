"""One chat turn, end to end. Used by the FastAPI endpoint and by the CLI.

    user JWT ──► connect_mcp (initialize) ──► read me/summary (who is this?) ──► tools/list
             ──► bind tools to the LLM ──► run/resume the graph ──► stream typed events

Events (each a dict with an "event" key; the HTTP layer turns them into SSE):
    thread              {thread_id}
    resource_read       {uri, request, response}             host read an MCP resource
    prompt_loaded       {name, messages}                     user invoked an MCP prompt
    token               {text}                               a piece of the assistant's reply
    tool_call_started   {id, tool, args, phase}              phase: "preview" (dry run) | "call"
    tool_call_result    {id, tool, phase, status, summary, structured?, request?, response?, is_write?}
    approval_required   {actions: [...]}                     graph paused, waiting for the user
    error               {message}
    done                {thread_id, awaiting_approval}
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from typing import Any, cast

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from mcp.client._transport import TransportStreams
from mcp.shared.exceptions import MCPError
from pydantic import SecretStr

from myshare_shared.tracing import configure_tracing

from .config import get_settings
from .graph.builder import AgentGraph
from .graph.nodes import ME_RESOURCE
from .graph.prompts import CONTEXT_NOTE
from .graph.state import HostContext
from .mcp_client import MCPConnection, connect_mcp, load_langchain_tools

log = logging.getLogger("myshare_host")

LLMFactory = Callable[[], BaseChatModel]
TransportFactory = Callable[[str], AbstractAsyncContextManager[TransportStreams]]


class HostError(Exception):
    pass


def default_llm() -> BaseChatModel:
    from langchain_anthropic import ChatAnthropic

    s = get_settings()
    if not s.anthropic_api_key:
        raise HostError("ANTHROPIC_API_KEY is not set. Add it to .env and restart the host.")
    # (Pydantic field aliases: model_name = model, max_tokens_to_sample = max_tokens.)
    # No temperature/top_p/top_k: current models (Sonnet 5.5, Opus 5.5) reject non-default
    # sampling values. They also think adaptively before answering, and thinking tokens
    # count toward max_tokens, so leave generous room or replies get cut off mid-answer.
    return ChatAnthropic(
        model_name=s.model_name,
        api_key=SecretStr(s.anthropic_api_key),
        max_tokens_to_sample=16000,
        timeout=120.0,
        stop=None,
    )


@dataclass
class TurnRequest:
    thread_id: str
    message: str | None = None
    resume: dict[str, Any] | None = None  # approval decisions
    prompt: dict[str, Any] | None = None  # {"name": "...", "arguments": {...}}


@dataclass
class ChatService:
    graph: AgentGraph
    llm_factory: LLMFactory = default_llm
    transport_factory: TransportFactory | None = None  # tests inject an in-memory transport
    recursion_limit: int = field(default_factory=lambda: get_settings().max_agent_steps * 4)

    def __post_init__(self) -> None:
        # Every entry point (web host, CLI, scripts) builds a ChatService, so this is where
        # the LangSmith privacy filter goes on, before the first traced LLM or tool call.
        configure_tracing("host")

    def connect(self, token: str) -> AbstractAsyncContextManager[MCPConnection]:
        transport = self.transport_factory(token) if self.transport_factory else None
        return connect_mcp(token, transport=transport)

    @staticmethod
    async def whoami(conn: MCPConnection) -> dict[str, Any]:
        """Identity via MCP: the summary resource is read with the user's own token."""
        return json.loads(await conn.read_text_resource(ME_RESOURCE))["user"]

    def config(self, user_id: int, thread_id: str) -> RunnableConfig:
        # Threads are namespaced by user, so one user can never load or resume another's thread.
        return {
            "configurable": {"thread_id": f"u{user_id}:{thread_id}"},
            "recursion_limit": self.recursion_limit,
        }

    async def run(self, token: str, req: TurnRequest) -> AsyncIterator[dict[str, Any]]:
        yield {"event": "thread", "thread_id": req.thread_id}
        awaiting = False
        try:
            base_llm = self.llm_factory()  # fail fast (e.g. missing API key) before connecting
            async with self.connect(token) as conn:
                try:
                    me = await self.whoami(conn)
                except MCPError as exc:
                    yield {
                        "event": "error",
                        "message": f"Could not load your profile: {exc}",
                        "auth": True,
                    }
                    return
                config = self.config(me["id"], req.thread_id)
                mcp_tools = await conn.list_tools()
                llm = base_llm.bind_tools(await load_langchain_tools(conn))
                ctx = HostContext(conn=conn, llm=llm, tools={t.name: t for t in mcp_tools})

                snapshot = await self.graph.aget_state(config)
                waiting = bool(snapshot.interrupts)
                if req.resume is not None:
                    if not waiting:
                        yield {
                            "event": "error",
                            "message": "There is no pending action to approve in this chat.",
                        }
                        return
                    graph_input: Any = Command(resume=req.resume)
                elif waiting:
                    yield {
                        "event": "error",
                        "message": "Please approve or reject the pending action first.",
                    }
                    yield {"event": "approval_required", **snapshot.interrupts[0].value}
                    awaiting = True
                    return
                elif req.prompt:
                    msgs = await self._prompt_messages(conn, req.prompt)
                    yield {
                        "event": "prompt_loaded",
                        "name": req.prompt["name"],
                        "messages": [{"role": _role(m), "text": m.text} for m in msgs],
                    }
                    if isinstance(msgs[-1], AIMessage):
                        # The prompt ends with the assistant speaking (e.g. asking questions):
                        # record it and wait for the user instead of calling the model.
                        await self.graph.aupdate_state(config, {"messages": msgs}, as_node="agent")
                        yield {"event": "token", "text": msgs[-1].text}
                        return
                    graph_input = {"messages": msgs}
                else:
                    graph_input = {"messages": [HumanMessage(req.message or "")]}

                # Three stream modes at once, yielded as (mode, chunk) pairs:
                #   messages: LLM token chunks
                #   custom:   events our nodes emit via runtime.stream_writer
                #   updates:  per-node state changes; an interrupt shows up as "__interrupt__"
                async for part in self.graph.astream(
                    graph_input, config, context=ctx, stream_mode=["messages", "custom", "updates"]
                ):
                    mode, chunk = cast(tuple[str, Any], part)
                    if mode == "messages":
                        msg, meta = chunk
                        if (
                            meta.get("langgraph_node") == "agent"
                            and isinstance(msg, AIMessageChunk)
                            and (text := _chunk_text(msg))
                        ):
                            yield {"event": "token", "text": text}
                    elif mode == "custom":
                        yield chunk
                    elif mode == "updates" and "__interrupt__" in chunk:
                        for intr in chunk["__interrupt__"]:
                            awaiting = True
                            yield {"event": "approval_required", **intr.value}
        except Exception as exc:
            root = _root_cause(exc)
            if not isinstance(root, HostError):
                log.exception("chat turn failed")
            yield {
                "event": "error",
                "message": str(root)
                if isinstance(root, HostError)
                else f"{type(root).__name__}: {root}",
            }
        finally:
            yield {"event": "done", "thread_id": req.thread_id, "awaiting_approval": awaiting}

    async def _prompt_messages(
        self, conn: MCPConnection, prompt: dict[str, Any]
    ) -> list[BaseMessage]:
        """`prompts/get` -> LangChain messages. The prompt's text becomes the conversation."""
        result = await conn.get_prompt(
            prompt["name"], {k: str(v) for k, v in (prompt.get("arguments") or {}).items()}
        )
        out: list[BaseMessage] = []
        for m in result.messages:
            text = getattr(m.content, "text", "")
            out.append(HumanMessage(text) if m.role == "user" else AIMessage(text))
        return out

    async def history(self, token: str, thread_id: str) -> dict[str, Any]:
        """Replay a thread for the UI (proves persistence: works after a host restart)."""
        async with self.connect(token) as conn:
            me = await self.whoami(conn)
        snap = await self.graph.aget_state(self.config(me["id"], thread_id))
        items: list[dict[str, Any]] = []
        for m in snap.values.get("messages", []):
            if isinstance(m, HumanMessage) and m.name == CONTEXT_NOTE:
                continue  # host-written context for the model, not something the user typed
            if isinstance(m, HumanMessage):
                items.append({"role": "user", "text": m.text})
            elif isinstance(m, AIMessage):
                items.append(
                    {
                        "role": "assistant",
                        "text": m.text,
                        "tool_calls": [
                            {"id": c["id"], "tool": c["name"], "args": c["args"]}
                            for c in m.tool_calls
                        ],
                    }
                )
            elif isinstance(m, ToolMessage):
                items.append(
                    {
                        "role": "tool",
                        "tool_call_id": m.tool_call_id,
                        "tool": m.name,
                        "status": m.status,
                    }
                )
        pending = snap.interrupts[0].value if snap.interrupts else None
        return {"thread_id": thread_id, "messages": items, "pending_approval": pending}


def _root_cause(exc: BaseException) -> BaseException:
    """MCP transports run in AnyIO task groups, so errors arrive wrapped in ExceptionGroups."""
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return exc


def _role(m: BaseMessage) -> str:
    return "user" if isinstance(m, HumanMessage) else "assistant"


def _chunk_text(msg: AIMessageChunk) -> str:
    """Text deltas only (Anthropic chunks are lists of blocks; tool-call JSON deltas are skipped)."""
    if isinstance(msg.content, str):
        return msg.content
    return "".join(
        b.get("text", "") for b in msg.content if isinstance(b, dict) and b.get("type") == "text"
    )
