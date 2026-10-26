"""The LangSmith privacy filter (myshare_shared/tracing.py): structure stays, content goes.

Synthetic data only. Nothing here talks to LangSmith.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from mcp.types import CallToolResult, TextContent

from myshare_shared.tracing import HIDDEN, parent_from_meta, redact

SECRET_BITS = ["Cab to airport", "1800", "Asha Rao", "asha@example.com", "Goa Trip", "owes you"]


def _assert_no_secrets(data: object) -> str:
    text = json.dumps(data)
    for bit in SECRET_BITS:
        assert bit not in text, f"{bit!r} leaked into the trace: {text}"
    return text


def test_llm_run_keeps_shape_and_hides_content() -> None:
    inputs = {
        "messages": [
            [
                SystemMessage("You are MyShare. Asha Rao owes you 1800."),
                HumanMessage("Add Cab to airport, 1800, Goa Trip"),
                AIMessage(
                    content=[
                        {"type": "text", "text": "Adding Cab to airport"},
                        {
                            "type": "tool_use",
                            "name": "add_expense",
                            "id": "toolu_1",
                            "input": {"description": "Cab to airport", "amount": "1800"},
                        },
                    ],
                    tool_calls=[
                        {
                            "name": "add_expense",
                            "args": {"group_id": 7, "description": "Cab to airport"},
                            "id": "toolu_1",
                            "type": "tool_call",
                        }
                    ],
                    usage_metadata={"input_tokens": 120, "output_tokens": 30, "total_tokens": 150},
                ),
                ToolMessage(
                    '{"name":"Asha Rao","email":"asha@example.com"}', tool_call_id="toolu_1"
                ),
            ]
        ]
    }
    out = redact(inputs)
    text = _assert_no_secrets(out)
    system, human, ai, tool = out["messages"][0]

    assert (system["type"], human["type"], tool["type"]) == ("system", "human", "tool")
    assert human["content"] == HIDDEN
    assert ai["content"][0] == {"type": "text", "text": HIDDEN}
    assert ai["content"][1]["name"] == "add_expense"  # tool names stay readable
    assert ai["tool_calls"][0]["name"] == "add_expense"
    assert ai["tool_calls"][0]["args"] == {"group_id": HIDDEN, "description": HIDDEN}
    assert ai["usage_metadata"]["total_tokens"] == 150  # token counts stay
    assert tool["tool_call_id"] == "toolu_1"
    assert "Asha" not in text


def test_tool_run_hides_arguments_and_result_but_keeps_flags() -> None:
    inputs = redact(
        {
            "tool": "add_expense",
            "arguments": {"description": "Cab to airport", "amount": "1800", "dry_run": True},
        }
    )
    assert inputs == {
        "tool": "add_expense",
        "arguments": {"description": HIDDEN, "amount": HIDDEN, "dry_run": True},
    }

    result = CallToolResult(
        content=[TextContent(type="text", text="Added Cab to airport, 1800, Goa Trip")],
        structured_content={"expense": {"id": 42, "description": "Cab to airport"}},
    )
    outputs = redact(result.model_dump(mode="json", exclude_none=True))
    _assert_no_secrets(outputs)
    assert outputs["is_error"] is False
    assert outputs["structured_content"]["expense"]["id"] == 42


def test_people_names_are_hidden_even_next_to_a_type() -> None:
    # "name" is only kept when the dict is a tool call/use; a person or group stays hidden.
    out = redact({"response": [{"name": "Asha Rao", "type": "friend"}, {"name": "Goa Trip"}]})
    assert out == {"response": [{"name": HIDDEN, "type": "friend"}, {"name": HIDDEN}]}


def test_never_raises_and_never_returns_raw_objects() -> None:
    class Weird:
        def __repr__(self) -> str:
            return "Asha Rao"

    @dataclass
    class Holder:
        thing: object
        note: str

    out = redact({"a": Weird(), "b": Holder(Weird(), "Goa Trip"), "c": {1, 2}})
    _assert_no_secrets(out)
    assert out["a"] == HIDDEN
    assert redact("just a string") == {"value": HIDDEN}


def test_parent_from_meta_only_accepts_the_trace_header() -> None:
    assert parent_from_meta(None) is None
    assert parent_from_meta({}) is None
    assert parent_from_meta({"langsmith-trace": ""}) is None
    assert parent_from_meta({"langsmith-trace": "x", "baggage": "langsmith-project=other"}) == {
        "langsmith-trace": "x"
    }
