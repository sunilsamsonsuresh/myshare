"""One chat turn with LangSmith tracing ON, uploads captured in memory (nothing leaves).

Checks the two things that matter before any trace is sent for real:
  * shape: agent -> tool run -> MCP server run -> REST API run, all in ONE trace,
    linked across the client/server boundary through the tools/call `_meta`;
  * privacy: names, emails, messages, replies and the user's JWT never appear.
"""

from __future__ import annotations

import json
from typing import Any

import langsmith
import pytest
import requests
from langchain_core.tracers.langchain import wait_for_all_tracers
from langsmith import run_trees

from myshare_shared import tracing
from tests.host.fake_llm import ScriptedChatModel, call, say
from tests.host.test_host_graph import make_service, run

pytestmark = pytest.mark.anyio


class CapturedUploads(langsmith.Client):
    """A LangSmith client whose HTTP calls (POST /runs, PATCH /runs/{id}) land in memory."""

    def __init__(self) -> None:
        super().__init__(
            api_key="lsv2_pt_test",
            api_url="http://langsmith.invalid",
            auto_batch_tracing=False,
            hide_inputs=tracing.redact,  # the same filter configure_tracing() installs
            hide_outputs=tracing.redact,
        )
        self.captured: dict[str, dict[str, Any]] = {}

    def request_with_retries(  # type: ignore[override]
        self, method: str, pathname: str, *_: Any, request_kwargs: Any = None, **__: Any
    ) -> requests.Response:
        data = (request_kwargs or {}).get("data") or b"{}"
        text = data.decode() if isinstance(data, bytes) else str(data)
        body = json.loads(text)
        run_id = str(body.get("id") or pathname.rstrip("/").rsplit("/", 1)[-1])
        self.captured.setdefault(run_id, {}).update(body)
        resp = requests.Response()
        resp.status_code, resp._content = 200, b"{}"
        return resp

    def named(self, name: str) -> dict[str, Any]:
        matches = [r for r in self.captured.values() if r.get("name") == name]
        assert len(matches) == 1, f"expected one run named {name!r}, got {len(matches)}"
        return matches[0]

    def parent_of(self, r: dict[str, Any]) -> dict[str, Any]:
        return self.captured[str(r["parent_run_id"])]


@pytest.fixture
def uploads(monkeypatch) -> CapturedUploads:
    cap = CapturedUploads()
    monkeypatch.setattr(run_trees, "_CLIENT", cap)  # the global client, as configure_tracing() sets
    monkeypatch.setattr(tracing, "_configured", True)  # keep the real client out of it
    return cap


async def test_traced_turn_is_one_linked_trace_with_content_hidden(
    people, trip, wire, saver, uploads
):
    me = people["me"]
    wire(me)
    llm = ScriptedChatModel(script=[call("list_groups", {}), say("You are in Goa Trip.")])
    svc = make_service(saver, llm)

    with langsmith.tracing_context(enabled=True, project_name="test"):
        events = await run(svc, me.token, message="Which groups am I in?")
    wait_for_all_tracers()
    assert events[-1]["event"] == "done"

    # Shape: LangGraph's "tools" node -> our MCP tool run -> the server's run -> the REST call.
    tool = uploads.named("list_groups")
    server = uploads.named("MCP server: list_groups")
    rest = uploads.named("GET /groups")
    assert tool["run_type"] == "tool"
    assert uploads.parent_of(tool)["name"] == "tools"
    assert server["parent_run_id"] == tool["id"]  # linked through tools/call _meta
    assert rest["parent_run_id"] == server["id"]
    assert len({r["trace_id"] for r in (tool, server, rest)}) == 1
    assert any(r.get("run_type") == "llm" for r in uploads.captured.values())
    assert tool["outputs"]["is_error"] is False

    # Privacy: nothing identifying, nothing the user or the model said, no credentials.
    # `serialized` is skipped: for this scripted test model it is a repr that includes its own
    # script. The real ChatAnthropic serializes only its settings (key as a secret reference).
    everything = json.dumps(
        [{k: v for k, v in r.items() if k != "serialized"} for r in uploads.captured.values()]
    )
    for secret in (
        "Goa Trip",
        "Which groups am I in?",
        "Priya",
        "Rahul",
        people["priya"].email,
        me.email,
        me.token,
    ):
        assert secret not in everything, f"{secret!r} was in an upload"
