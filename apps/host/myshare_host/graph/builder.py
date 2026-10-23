"""Assemble the LangGraph state machine explicitly (no prebuilt agent)."""

from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from . import nodes
from .state import AgentState, HostContext

AgentGraph = CompiledStateGraph[AgentState, HostContext, AgentState, AgentState]


def build_graph(checkpointer: BaseCheckpointSaver) -> AgentGraph:
    g = StateGraph(AgentState, context_schema=HostContext)
    g.add_node("load_context", nodes.load_context)
    g.add_node("agent", nodes.agent)
    g.add_node("prepare_approval", nodes.prepare_approval)
    g.add_node("approval", nodes.approval)
    g.add_node("tools", nodes.tools)

    g.add_edge(START, "load_context")
    g.add_edge("load_context", "agent")
    g.add_conditional_edges("agent", nodes.route_after_agent, ["tools", "prepare_approval", END])
    g.add_conditional_edges("prepare_approval", nodes.route_after_prepare, ["approval", "tools"])
    g.add_edge("approval", "tools")
    g.add_edge("tools", "agent")  # loop until the model stops calling tools

    # The checkpointer saves state after every step, keyed by thread_id. That is what
    # makes conversations survive restarts and lets an interrupted run resume later.
    return g.compile(checkpointer=checkpointer)
