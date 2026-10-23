"""The host's hand-built MCP client layer.

connection.py  open/initialize/close a ClientSession over Streamable HTTP or stdio
tools.py       MCP tool definitions -> LangChain tools; approval policy; result framing
wire.py        record raw JSON-RPC traffic (debug transcript + UI inspector)
"""

from .connection import MCPConnection, connect_mcp
from .tools import (
    frame_for_llm,
    load_langchain_tools,
    needs_approval,
    result_text,
    supports_dry_run,
)

__all__ = [
    "MCPConnection",
    "connect_mcp",
    "frame_for_llm",
    "load_langchain_tools",
    "needs_approval",
    "result_text",
    "supports_dry_run",
]
