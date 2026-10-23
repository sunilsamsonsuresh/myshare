"""MCP server tests: a real MCP client talks to the server in-process.

`Client(mcp, mode="legacy")` connects over in-memory streams using the classic
`initialize` handshake and real JSON-RPC framing, so this exercises the same
protocol path as stdio. The server's REST calls go to the in-memory test API.
With no HTTP headers in-process, the user's token comes from MYSHARE_USER_TOKEN
(exactly like stdio mode).
"""

from __future__ import annotations

import json

import httpx
import pytest
from mcp import Client

from myshare_mcp import api_client
from myshare_mcp.server import mcp
from tests.conftest import Person, signup

pytestmark = pytest.mark.anyio

READ_TOOLS = {
    "resolve_person",
    "list_friends",
    "list_groups",
    "get_group_details",
    "get_balances",
    "list_expenses",
    "search_expenses",
    "get_simplified_debts",
}
WRITE_TOOLS = {
    "add_expense",
    "update_expense",
    "delete_expense",
    "settle_up",
    "create_group",
    "add_friend",
}


@pytest.fixture
def as_user(api_app, monkeypatch):
    """Route the MCP server's API calls to the in-memory API; pick the acting user."""
    api_client.use_transport(httpx.ASGITransport(app=api_app))
    monkeypatch.setenv("MYSHARE_API_URL", "http://api.test")

    def _as(p: Person) -> None:
        monkeypatch.setenv("MYSHARE_USER_TOKEN", p.token)

    yield _as
    api_client.use_transport(None)


@pytest.fixture
async def mcp_client():
    async with Client(mcp, mode="legacy") as c:
        yield c


async def call(c: Client, tool: str, **args):
    r = await c.call_tool(tool, args)
    return r


def text(r) -> str:
    return r.content[0].text


# ---------------------------------------------------------------- discovery
async def test_initialize_and_capabilities(mcp_client):
    assert mcp_client.server_info is not None and mcp_client.server_info.name == "myshare"
    caps = mcp_client.server_capabilities
    assert caps.tools is not None and caps.resources is not None and caps.prompts is not None
    assert "Never guess numeric ids" in (mcp_client.instructions or "")


async def test_tool_schemas_and_annotations(mcp_client):
    tools = {t.name: t for t in (await mcp_client.list_tools()).tools}
    assert set(tools) == READ_TOOLS | WRITE_TOOLS
    for name in READ_TOOLS:
        assert tools[name].annotations.read_only_hint is True
    for name in WRITE_TOOLS:
        assert tools[name].annotations.read_only_hint is False
        assert "dry_run" in tools[name].input_schema["properties"]
    assert tools["delete_expense"].annotations.destructive_hint is True
    assert all(t.output_schema for t in tools.values()), "every tool publishes an outputSchema"
    assert set(tools["add_expense"].input_schema["required"]) == {"description", "amount", "split"}
    assert tools["get_balances"].input_schema["properties"]["scope"]["enum"] == [
        "overall",
        "friend",
        "group",
    ]


# ---------------------------------------------------------------- read tools
async def test_read_tools(client, people, trip, as_user, mcp_client):
    me, priya = people["me"], people["priya"]
    as_user(me)
    await call(
        mcp_client,
        "add_expense",
        description="Dinner",
        amount="300",
        group_id=trip,
        split={"type": "equal"},
    )

    r = await call(mcp_client, "list_groups")
    assert not r.is_error
    assert r.structured_content["groups"][0]["name"] == "Goa Trip"
    assert r.structured_content["groups"][0]["your_balance"] == {
        "amount": "200.00",
        "currency": "INR",
        "display": "₹200.00",
    }

    r = await call(mcp_client, "get_group_details", group_id=trip)
    sc = r.structured_content
    assert [m["name"] for m in sc["members"]] == ["Me", "Priya", "Rahul"]
    assert sc["recent_expenses"][0]["description"] == "Dinner"
    assert "Members: Me (id" in text(r)

    r = await call(mcp_client, "list_friends")
    assert {f["name"]: f["status"] for f in r.structured_content["friends"]} == {
        "Priya": "owes you",
        "Rahul": "owes you",
    }

    r = await call(mcp_client, "get_balances")
    assert "You are owed ₹200.00" in text(r)
    r = await call(mcp_client, "get_balances", scope="friend", id=priya.id)
    assert r.structured_content["friend"]["balances"][0]["amount"] == "100.00"
    r = await call(mcp_client, "get_balances", scope="group", id=trip)
    assert r.structured_content["group"]["name"] == "Goa Trip"

    r = await call(mcp_client, "list_expenses", group_id=trip, limit=5)
    e = r.structured_content["expenses"][0]
    assert e["amount"]["display"] == "₹300.00" and e["your_net"]["amount"] == "200.00"
    assert (await call(mcp_client, "search_expenses", query="dinn")).structured_content[
        "count"
    ] == 1
    assert (await call(mcp_client, "search_expenses", query="zzz")).structured_content["count"] == 0

    r = await call(mcp_client, "get_simplified_debts", group_id=trip)
    assert r.structured_content["after_count"] == 2
    assert "Priya pays Me ₹100.00" in text(r)


async def test_resolve_person_unique_ambiguous_not_found(client, people, trip, as_user, mcp_client):
    me = people["me"]
    priyanka = signup(client, "Priyanka")
    client.post(f"/groups/{trip}/members", json={"email": priyanka.email}, headers=me.h)
    as_user(me)

    r = await call(mcp_client, "resolve_person", name="rahul")
    assert r.structured_content["status"] == "unique"
    assert r.structured_content["matches"][0]["id"] == people["rahul"].id

    r = await call(mcp_client, "resolve_person", name="pri")
    assert r.structured_content["status"] == "ambiguous"
    assert {m["name"] for m in r.structured_content["matches"]} == {"Priya", "Priyanka"}
    assert "do not guess" in r.structured_content["hint"]

    r = await call(mcp_client, "resolve_person", name="Mallory")  # exists, but not connected to me
    assert r.structured_content["status"] == "not_found"
    assert "add_friend" in r.structured_content["hint"]


# ---------------------------------------------------------------- write tools
async def test_add_expense_dry_run_then_real(client, people, trip, as_user, mcp_client):
    me, priya, rahul = people["me"], people["priya"], people["rahul"]
    as_user(me)
    args = dict(description="Cab", amount="1800", group_id=trip, split={"type": "equal"})

    r = await call(mcp_client, "add_expense", **args, dry_run=True)
    assert not r.is_error, text(r)
    assert r.structured_content["preview"] is True
    assert text(r).startswith("PREVIEW (nothing saved)")
    assert client.get(f"/expenses?group_id={trip}", headers=me.h).json() == []

    r = await call(mcp_client, "add_expense", **args)
    sc = r.structured_content
    assert sc["action"] == "created" and sc["preview"] is False
    assert [s["owes"]["display"] for s in sc["expense"]["split"]] == ["₹600.00"] * 3
    assert sc["expense"]["paid_by"]["id"] == me.id  # payer defaults to the current user
    saved = client.get(f"/expenses?group_id={trip}", headers=me.h).json()
    assert saved[0]["amount"] == 180000  # stored as paise

    # exact split given in human decimals -> converted to minor units by the MCP server
    r = await call(
        mcp_client,
        "add_expense",
        description="Snacks",
        amount="100.50",
        group_id=trip,
        payer_id=priya.id,
        split={
            "type": "exact",
            "participants": [
                {"user_id": me.id, "value": "60.25"},
                {"user_id": rahul.id, "value": "40.25"},
            ],
        },
    )
    assert not r.is_error, text(r)
    assert {s["name"]: s["owes"]["amount"] for s in r.structured_content["expense"]["split"]} == {
        "Me": "60.25",
        "Rahul": "40.25",
    }


async def test_update_and_delete_expense(client, people, trip, as_user, mcp_client):
    me = people["me"]
    as_user(me)
    eid = (
        await call(
            mcp_client,
            "add_expense",
            description="Lunch",
            amount=900,
            group_id=trip,
            split={"type": "equal"},
        )
    ).structured_content["expense"]["id"]

    r = await call(
        mcp_client, "update_expense", expense_id=eid, amount="1200", description="Brunch"
    )
    assert r.structured_content["expense"]["amount"]["display"] == "₹1,200.00"
    assert r.structured_content["expense"]["description"] == "Brunch"

    r = await call(mcp_client, "delete_expense", expense_id=eid, dry_run=True)
    assert "would delete" in text(r)
    assert client.get(f"/expenses/{eid}", headers=me.h).status_code == 200

    r = await call(mcp_client, "delete_expense", expense_id=eid)
    assert r.structured_content["action"] == "deleted"
    assert client.get(f"/expenses/{eid}", headers=me.h).status_code == 404


async def test_settle_up_create_group_add_friend(client, people, trip, as_user, mcp_client):
    me, rahul, ananya = people["me"], people["rahul"], people["ananya"]
    as_user(me)
    r = await call(
        mcp_client,
        "settle_up",
        from_user_id=rahul.id,
        to_user_id=me.id,
        amount="250",
        group_id=trip,
    )
    assert text(r).startswith("Recorded: Rahul paid Me ₹250.00")

    r = await call(mcp_client, "add_friend", email=ananya.email)
    assert r.structured_content["friend"]["name"] == "Ananya"

    r = await call(
        mcp_client, "create_group", name="Flat", member_emails=[ananya.email], kind="home"
    )
    assert [m["name"] for m in r.structured_content["group"]["members"]] == ["Me", "Ananya"]


# ---------------------------------------------------------------- errors the LLM can act on
async def test_error_messages_are_actionable(client, people, trip, as_user, mcp_client):
    me, ananya, mallory = people["me"], people["ananya"], people["mallory"]
    as_user(me)

    r = await call(
        mcp_client,
        "add_expense",
        description="x",
        amount="100",
        group_id=trip,
        split={"type": "equal", "participants": [{"user_id": ananya.id}]},
    )
    assert r.is_error
    assert (
        "aren't part of" in text(r) and "Priya" in text(r) and "Rahul" in text(r)
    )  # lists valid members

    r = await call(
        mcp_client,
        "add_expense",
        description="x",
        amount="10.005",
        group_id=trip,
        split={"type": "equal"},
    )
    assert r.is_error and "too many decimal places" in text(r) and "10.01" in text(r)

    r = await call(
        mcp_client,
        "add_expense",
        description="x",
        amount="100",
        group_id=trip,
        split={"type": "percent", "participants": [{"user_id": me.id, "value": "50"}]},
    )
    assert r.is_error and "add up to exactly 100" in text(r)

    as_user(mallory)
    r = await call(mcp_client, "get_group_details", group_id=trip)
    assert r.is_error and "not a member" in text(r)


async def test_missing_token_is_reported(monkeypatch, api_app, mcp_client):
    monkeypatch.delenv("MYSHARE_USER_TOKEN", raising=False)
    r = await call(mcp_client, "list_groups")
    assert r.is_error and "Not authenticated" in text(r)


# ---------------------------------------------------------------- resources & prompts
async def test_resources(client, people, trip, as_user, mcp_client):
    as_user(people["me"])
    static = {str(r.uri) for r in (await mcp_client.list_resources()).resources}
    assert static == {"myshare://me/summary"}
    templates = {
        t.uri_template for t in (await mcp_client.list_resource_templates()).resource_templates
    }
    assert templates == {"myshare://groups/{group_id}", "myshare://groups/{group_id}/activity"}

    me = json.loads((await mcp_client.read_resource("myshare://me/summary")).contents[0].text)
    assert me["user"]["name"] == "Me" and me["group_count"] == 1

    g = json.loads((await mcp_client.read_resource(f"myshare://groups/{trip}")).contents[0].text)
    assert g["name"] == "Goa Trip"
    acts = json.loads(
        (await mcp_client.read_resource(f"myshare://groups/{trip}/activity")).contents[0].text
    )
    assert "created the group" in acts[0]["what"]


async def test_prompts(mcp_client):
    prompts = {p.name: p for p in (await mcp_client.list_prompts()).prompts}
    assert set(prompts) == {"settle_up_plan", "monthly_summary", "split_receipt"}
    assert [a.name for a in prompts["monthly_summary"].arguments] == ["month"]

    r = await mcp_client.get_prompt("monthly_summary", {"month": "2026-09"})
    body = r.messages[0].content.text
    assert "September 2026" in body and "since=2026-09-01" in body and "until=2026-09-30" in body

    r = await mcp_client.get_prompt("split_receipt", {"description": "Dinner ₹4,200"})
    assert [m.role for m in r.messages] == ["user", "assistant"]
