"""A scripted chat model: returns pre-written AIMessages (text and/or tool calls) in order.

It implements both _generate and _stream so LangGraph's "messages" stream mode
produces real token events, just like ChatAnthropic does.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.messages.tool import tool_call_chunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import Field


def say(text: str) -> AIMessage:
    return AIMessage(content=text)


def call(name: str, args: dict[str, Any], *, id: str | None = None, text: str = "") -> AIMessage:
    return AIMessage(
        content=text,
        tool_calls=[{"name": name, "args": args, "id": id or f"call_{name}", "type": "tool_call"}],
    )


class ScriptedChatModel(BaseChatModel):
    script: list[AIMessage] = Field(default_factory=list)
    seen: list[list[BaseMessage]] = Field(default_factory=list)  # every prompt the model received
    bound_tools: list[Any] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Any, **kwargs: Any) -> ScriptedChatModel:  # type: ignore[override]
        self.bound_tools = list(tools)
        return self

    def _next(self, messages: list[BaseMessage]) -> AIMessage:
        self.seen.append(list(messages))
        if not self.script:
            raise AssertionError("ScriptedChatModel ran out of scripted replies")
        return self.script.pop(0)

    def _generate(
        self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None, **kw: Any
    ) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self._next(messages))])

    def _stream(
        self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None, **kw: Any
    ) -> Iterator[ChatGenerationChunk]:
        msg = self._next(messages)
        text = msg.content if isinstance(msg.content, str) else ""
        for word in text.split(" ") if text else []:
            chunk = ChatGenerationChunk(message=AIMessageChunk(content=word + " "))
            if run_manager:
                run_manager.on_llm_new_token(chunk.text, chunk=chunk)
            yield chunk
        if msg.tool_calls:
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content="",
                    tool_call_chunks=[
                        tool_call_chunk(
                            name=c["name"], args=json.dumps(c["args"]), id=c["id"], index=i
                        )
                        for i, c in enumerate(msg.tool_calls)
                    ],
                )
            )
