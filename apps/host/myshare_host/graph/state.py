"""Graph state (checkpointed per thread) and run context (per request, never stored)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, Literal, NotRequired, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AnyMessage
from langchain_core.runnables import Runnable
from langgraph.graph.message import add_messages
from mcp.types import Tool

from ..mcp_client import MCPConnection


class PendingAction(TypedDict):
    """One write the user must approve: rendered as an approval card."""

    tool_call_id: str
    tool: str
    title: str
    args: dict[str, Any]
    preview: str  # human sentence from the dry run, e.g. 'would add "Cab" ₹1,800.00 ...'
    details: dict[str, Any] | None  # structured dry-run result (split lines etc.)
    destructive: bool


class Decision(TypedDict):
    action: Literal["approve", "reject", "edit", "invalid"]
    feedback: NotRequired[str]  # reject reason / requested changes
    message: NotRequired[str]  # for "invalid": the dry-run error to hand back to the model


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    user_context: NotRequired[str]  # the last context note added to messages (me/summary + date)
    gated_tools: NotRequired[list[str]]  # tool names that need approval (from annotations)
    pending: NotRequired[list[PendingAction]]
    decisions: NotRequired[dict[str, Decision]]  # tool_call_id -> decision


@dataclass
class HostContext:
    """Live objects for one run. LangGraph passes this to nodes as `runtime.context`.

    It is NOT checkpointed: an MCP connection can't be serialized, and a resumed
    thread gets a fresh connection with the current user's token.
    """

    conn: MCPConnection
    llm: Runnable | BaseChatModel  # chat model with the MCP-derived tools already bound
    tools: dict[str, Tool]  # MCP tool definitions by name
