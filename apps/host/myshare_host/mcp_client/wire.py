"""A wire tap for MCP: record every raw JSON-RPC message between client and server.

A transport (stdio or Streamable HTTP) hands the client a pair of streams:
    read_stream  - messages FROM the server (responses, notifications, server requests)
    write_stream - messages TO the server   (requests, notifications)

`ClientSession` only sees these two streams; it doesn't care which transport
produced them. That's the layering MCP is built on: JSON-RPC messages over any
pipe. We slip a thin wrapper around each stream that records the message and
passes it through unchanged. This is how docs/MCP_EXPLAINED.md got its real
transcript, and how the chat UI shows the raw request/response for a tool call.

Set MCP_DEBUG_WIRE=1 to also print every message to stderr and append it to
logs/mcp_wire.jsonl.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import sys
from pathlib import Path
from types import TracebackType
from typing import Any, Literal, Self

from mcp.client._transport import ReadStream, WriteStream
from mcp.shared.message import SessionMessage

log = logging.getLogger("myshare_host.wire")
WIRE_LOG = Path("logs/mcp_wire.jsonl")


def _jsonable(item: SessionMessage | Exception) -> dict[str, Any]:
    if isinstance(item, Exception):
        return {"transport_error": repr(item)}
    # `message` is a pydantic JSONRPCRequest/Response/Notification/Error; dump it with
    # wire (camelCase) names, exactly as it is serialized onto the transport.
    return item.message.model_dump(mode="json", by_alias=True, exclude_none=True)


class WireTap:
    def __init__(self, debug: bool = False, label: str = ""):
        self.debug = debug
        self.label = label
        self.messages: list[dict[str, Any]] = []  # {"dir": "send"|"recv", "msg": {...}}

    def record(self, direction: Literal["send", "recv"], item: SessionMessage | Exception) -> None:
        msg = _jsonable(item)
        self.messages.append({"dir": direction, "msg": msg})
        if self.debug:
            arrow = "host -> server" if direction == "send" else "server -> host"
            line = json.dumps(msg, ensure_ascii=False)
            print(f"[mcp wire {self.label}] {arrow}: {line}", file=sys.stderr)
            WIRE_LOG.parent.mkdir(exist_ok=True)
            with WIRE_LOG.open("a") as f:
                f.write(
                    json.dumps(
                        {"ts": dt.datetime.now(dt.UTC).isoformat(), "dir": direction, "msg": msg}
                    )
                    + "\n"
                )

    def last_exchange(self, method: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        """The most recent request with this method and the response that answered it."""
        for i in range(len(self.messages) - 1, -1, -1):
            m = self.messages[i]
            if m["dir"] == "send" and m["msg"].get("method") == method:
                req = m["msg"]
                resp = next(
                    (
                        n["msg"]
                        for n in self.messages[i + 1 :]
                        if n["dir"] == "recv" and n["msg"].get("id") == req.get("id")
                    ),
                    None,
                )
                return req, resp
        return None, None

    def wrap(
        self, read: ReadStream[SessionMessage | Exception], write: WriteStream[SessionMessage]
    ) -> tuple[ReadStream[SessionMessage | Exception], WriteStream[SessionMessage]]:
        return _TapRead(read, self), _TapWrite(write, self)


class _TapRead:
    def __init__(self, inner: ReadStream[SessionMessage | Exception], tap: WireTap):
        self._inner, self._tap = inner, tap

    async def receive(self) -> SessionMessage | Exception:
        item = await self._inner.receive()
        self._tap.record("recv", item)
        return item

    def __aiter__(self) -> Self:
        return self

    async def __anext__(self) -> SessionMessage | Exception:
        item = await self._inner.__anext__()
        self._tap.record("recv", item)
        return item

    async def aclose(self) -> None:
        await self._inner.aclose()

    async def __aenter__(self) -> Self:
        await self._inner.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool | None:
        return await self._inner.__aexit__(exc_type, exc_val, exc_tb)

    def __getattr__(self, name: str) -> Any:  # e.g. `last_context`, read by the SDK if present
        return getattr(self._inner, name)


class _TapWrite:
    def __init__(self, inner: WriteStream[SessionMessage], tap: WireTap):
        self._inner, self._tap = inner, tap

    async def send(self, item: SessionMessage, /) -> None:
        self._tap.record("send", item)
        await self._inner.send(item)

    async def aclose(self) -> None:
        await self._inner.aclose()

    async def __aenter__(self) -> Self:
        await self._inner.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool | None:
        return await self._inner.__aexit__(exc_type, exc_val, exc_tb)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)
