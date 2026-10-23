"""The MyShare MCP server: MyShare's capabilities, described for any MCP host.

This module exposes all three MCP primitives:

    TOOLS      model-controlled.   The LLM decides when to call them (list_groups, add_expense...).
    RESOURCES  application-controlled. The HOST decides when to read them and put them
               into context (myshare://me/summary is read on every chat turn).
    PROMPTS    user-controlled.    The USER picks them, e.g. as /settle_up_plan in the chat UI.

The server knows nothing about LLMs. It works unchanged with the MCP Inspector,
Claude Desktop, or our own LangGraph host. Every capability is a thin adapter over
the MyShare REST API, called with the end user's own token (see auth.py).
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ResourceError, ToolError
from mcp.server.mcpserver.prompts.base import AssistantMessage, Message, UserMessage
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import BaseModel, Field

from myshare_shared.money import MoneyError, to_minor

from . import views as v
from .api_client import MyShareAPI
from .auth import capture_request_headers, user_token

log = logging.getLogger("myshare_mcp")

INSTRUCTIONS = """\
MyShare tracks shared expenses between friends and in groups (like Splitwise).
- Never guess numeric ids. Get them from list_groups, list_friends, get_group_details or resolve_person.
- Amounts are decimal strings in the group's currency (e.g. "1200.50"); the server converts them.
- Write tools accept dry_run=true to preview exactly what would happen without saving.
"""

mcp = MCPServer(
    name="myshare",
    title="MyShare",
    version="0.1.0",
    instructions=INSTRUCTIONS,  # sent to the client during initialization
    middleware=[capture_request_headers],  # makes the caller's HTTP headers available (auth.py)
)


# --------------------------------------------------------------------------- helpers
def api() -> MyShareAPI:
    """An API client acting AS THE CURRENT USER (their token, not a service account)."""
    return MyShareAPI(user_token())


def reply(summary: str, data: BaseModel) -> CallToolResult:
    """Build a tool result with both a human summary and structured content.

    * structured_content: machine-readable, validated against the tool's outputSchema.
    * content (text): what a model or human reads. We include the short summary AND
      the JSON, because many hosts only forward `content` to the LLM.
    """
    payload = data.model_dump(mode="json", exclude_none=True)
    text = f"{summary}\n\n{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}"
    return CallToolResult(content=[TextContent(type="text", text=text)], structured_content=payload)


# Annotations are HINTS for the host (MCP spec: never trust them for security from an
# untrusted server). Our host uses them to decide which calls need human approval.
READ = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)
WRITE = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False
)
WRITE_IDEMPOTENT = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)
DESTRUCTIVE = ToolAnnotations(
    read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=False
)

DryRun = Annotated[
    bool,
    Field(
        description="Preview only: validate and return exactly what would happen, without saving anything."
    ),
]
Amount = Annotated[
    str | float,
    Field(
        description='Amount in currency units as a decimal, e.g. "1200" or "1200.50" (NOT paise/cents).'
    ),
]


async def _group_or_friend_currency(
    client: MyShareAPI, group_id: int | None, friend_id: int | None, currency: str | None
) -> str:
    if currency:
        return currency.upper()
    if group_id is not None:
        return (await client.get(f"/groups/{group_id}"))["currency"]
    return (await client.get("/users/me/summary"))["default_currency"]


def _minor(amount: str | float, currency: str, what: str = "amount") -> int:
    try:
        return to_minor(amount, currency)
    except MoneyError as exc:
        raise ToolError(f"Invalid {what}: {exc}") from None


def _friend(f: dict[str, Any]) -> v.FriendBalance:
    raw = f.get("balances", [])
    return v.FriendBalance(
        id=f["id"],
        name=f["name"],
        email=f["email"],
        balances=[v.money(b["amount"], b["currency"]) for b in raw],
        status=v.status_of(raw[0]["amount"] if raw else 0),
    )


def _group_details(g: dict[str, Any], recent: list[dict[str, Any]] | None = None) -> v.GroupDetails:
    cur = g["currency"]
    return v.GroupDetails(
        id=g["id"],
        name=g["name"],
        kind=g["kind"],
        currency=cur,
        members=[
            v.Member(
                id=m["id"],
                name=m["name"],
                email=m["email"],
                balance=v.money(m["balance"], cur),
                status=v.status_of(m["balance"])
                .replace("owes you", "is owed")
                .replace("you owe", "owes"),
            )
            for m in g["members"]
        ],
        total_spent=v.money(g["total_spent"], cur),
        expense_count=g["expense_count"],
        your_balance=v.money(g["my_balance"], cur),
        recent_expenses=[v.expense_item(e) for e in (recent or [])],
    )


# =========================================================================== TOOLS: read
@mcp.tool(title="Find a person", annotations=READ)
async def resolve_person(
    name: Annotated[
        str,
        Field(
            description='A name, partial name or email, e.g. "Rahul" or "priya@". Use "me" for the current user.'
        ),
    ],
) -> Annotated[CallToolResult, v.ResolvePersonResult]:
    """Look up the user id of someone the current user knows (friends and group co-members).

    Call this whenever the user mentions a person by name, BEFORE using their id in another tool.
    If the result is ambiguous, ask the user which person they meant; never pick one yourself.
    """
    async with api() as c:
        r = await c.get("/people/resolve", name=name)
    matches = [v.PersonMatch(**m) for m in r["matches"]]
    if not matches:
        status, hint = (
            "not_found",
            (
                f'Nobody named "{name}" among the user\'s friends or groups. Ask the user for their email '
                "and use add_friend, or check the spelling."
            ),
        )
    elif len(matches) == 1:
        status, hint = "unique", f"Use id {matches[0].id} for {matches[0].name}."
    else:
        status, hint = (
            "ambiguous",
            "Several people match. Ask the user which one they mean; do not guess.",
        )
    summary = {
        "unique": f'"{name}" is {matches[0].name} (id {matches[0].id}).' if matches else "",
        "ambiguous": f'"{name}" matches {len(matches)} people: '
        + ", ".join(f"{m.name} (id {m.id}, {m.via})" for m in matches),
        "not_found": f'No one called "{name}" found.',
    }[status]
    return reply(
        summary, v.ResolvePersonResult(query=name, status=status, matches=matches, hint=hint)
    )


@mcp.tool(title="List friends", annotations=READ)
async def list_friends() -> Annotated[CallToolResult, v.FriendsResult]:
    """List the current user's friends with the net balance with each (positive = they owe the user)."""
    async with api() as c:
        friends = [_friend(f) for f in await c.get("/friends")]
    lines = [
        f"{f.name}: {f.balances[0].display if f.balances else '₹0'} ({f.status})" for f in friends
    ]
    return reply(f"{len(friends)} friends. " + "; ".join(lines), v.FriendsResult(friends=friends))


@mcp.tool(title="List groups", annotations=READ)
async def list_groups() -> Annotated[CallToolResult, v.GroupsResult]:
    """List the groups the current user belongs to, with their balance in each."""
    async with api() as c:
        gs = await c.get("/groups")
    groups = [
        v.GroupSummary(
            id=g["id"],
            name=g["name"],
            kind=g["kind"],
            currency=g["currency"],
            member_count=g["member_count"],
            your_balance=v.money(g["my_balance"], g["currency"]),
            status=v.status_of(g["my_balance"]).replace("owes you", "you are owed"),
        )
        for g in gs
    ]
    return reply(
        f"{len(groups)} groups: " + ", ".join(f"{g.name} (id {g.id})" for g in groups),
        v.GroupsResult(groups=groups),
    )


@mcp.tool(title="Group details", annotations=READ)
async def get_group_details(
    group_id: Annotated[int, Field(description="Group id from list_groups")],
) -> Annotated[CallToolResult, v.GroupDetails]:
    """Members (with ids and balances), total spent and the 5 most recent expenses of a group."""
    async with api() as c:
        g = await c.get(f"/groups/{group_id}")
        recent = await c.get("/expenses", group_id=group_id, limit=5)
    d = _group_details(g, recent)
    members = ", ".join(f"{m.name} (id {m.id}) {m.balance.display}" for m in d.members)
    return reply(
        f'"{d.name}" ({d.currency}), total spent {d.total_spent.display}. Members: {members}.', d
    )


@mcp.tool(title="Get balances", annotations=READ)
async def get_balances(
    scope: Annotated[
        Literal["overall", "friend", "group"],
        Field(
            description="overall = totals across everything; friend = with one friend; group = everyone in one group"
        ),
    ] = "overall",
    id: Annotated[
        int | None, Field(description="Friend's user id (scope=friend) or group id (scope=group)")
    ] = None,
) -> Annotated[CallToolResult, v.BalancesResult]:
    """Who owes whom. Positive amounts mean money is owed TO the current user."""
    async with api() as c:
        r = await c.get("/balances", scope=scope, id=id)
    if scope == "overall":
        lines = [
            v.OverallLine(
                currency=b["currency"],
                owed_to_you=v.money(b["owed_to_you"], b["currency"]),
                you_owe=v.money(b["you_owe"], b["currency"]),
                net=v.money(b["net"], b["currency"]),
            )
            for b in r["overall"]
        ]
        text = "; ".join(
            f"You are owed {b.owed_to_you.display} and you owe {b.you_owe.display}" for b in lines
        )
        return reply(
            text or "You are all settled up.", v.BalancesResult(scope="overall", overall=lines)
        )
    if scope == "friend":
        f = r["friend"]
        friend = _friend(f)
        breakdown = [
            v.FriendGroupLine(
                group_id=b["group_id"],
                group=b["group_name"],
                balances=[v.money(x["amount"], x["currency"]) for x in b["balances"]],
            )
            for b in f["breakdown"]
        ]
        text = f"{friend.name}: {friend.balances[0].display if friend.balances else '0'} ({friend.status})"
        return reply(
            text, v.BalancesResult(scope="friend", friend=friend, friend_breakdown=breakdown)
        )
    g = _group_details(r["group"])
    text = f'"{g.name}": ' + ", ".join(f"{m.name} {m.balance.display}" for m in g.members)
    return reply(text, v.BalancesResult(scope="group", group=g))


@mcp.tool(title="List expenses", annotations=READ)
async def list_expenses(
    group_id: Annotated[int | None, Field(description="Only this group's expenses")] = None,
    friend_id: Annotated[
        int | None, Field(description="Only expenses shared with this friend")
    ] = None,
    limit: Annotated[int, Field(ge=1, le=50, description="Max results (newest first)")] = 10,
    since: Annotated[
        str | None, Field(description="ISO date YYYY-MM-DD; only expenses on/after this date")
    ] = None,
    until: Annotated[
        str | None, Field(description="ISO date YYYY-MM-DD; only expenses on/before this date")
    ] = None,
) -> Annotated[CallToolResult, v.ExpensesResult]:
    """Recent expenses visible to the user, newest first. Each has an id usable with update_expense/delete_expense."""
    async with api() as c:
        rows = await c.get(
            "/expenses",
            group_id=group_id,
            friend_id=friend_id,
            limit=limit,
            since=since,
            until=until,
        )
    items = [v.expense_item(e) for e in rows]
    note = (
        f"Showing the newest {limit}; narrow with since/until or raise limit."
        if len(items) == limit
        else None
    )
    text = f"{len(items)} expenses: " + "; ".join(
        f"#{e.id} {e.date} {e.description} {e.amount.display} paid by {e.paid_by.name}"
        for e in items
    )
    return reply(text, v.ExpensesResult(expenses=items, count=len(items), note=note))


@mcp.tool(title="Search expenses", annotations=READ)
async def search_expenses(
    query: Annotated[
        str, Field(min_length=1, description='Text to look for in descriptions, e.g. "cab"')
    ],
    limit: Annotated[int, Field(ge=1, le=50)] = 10,
) -> Annotated[CallToolResult, v.ExpensesResult]:
    """Find expenses whose description contains the given text (case-insensitive)."""
    async with api() as c:
        rows = await c.get("/expenses", q=query, limit=limit)
    items = [v.expense_item(e) for e in rows]
    text = f'{len(items)} expenses match "{query}": ' + "; ".join(
        f"#{e.id} {e.date} {e.description} {e.amount.display}" for e in items
    )
    return reply(text, v.ExpensesResult(expenses=items, count=len(items)))


@mcp.tool(title="Simplest way to settle a group", annotations=READ)
async def get_simplified_debts(
    group_id: Annotated[int, Field(description="Group id from list_groups")],
) -> Annotated[CallToolResult, v.SimplifiedDebtsResult]:
    """The minimum set of payments that settles everyone in a group (debt simplification)."""
    async with api() as c:
        r = await c.get(f"/groups/{group_id}/simplified-debts")
    cur = r["currency"]
    transfers = [
        v.Transfer(
            from_person=v.person(t["from_user"]),
            to_person=v.person(t["to_user"]),
            amount=v.money(t["amount"], cur),
        )
        for t in r["transfers"]
    ]
    text = (
        f'"{r["group_name"]}" is settled up.'
        if not transfers
        else f'To settle "{r["group_name"]}" in {len(transfers)} payments (instead of {r["original_transfer_count"]}): '
        + "; ".join(
            f"{t.from_person.name} pays {t.to_person.name} {t.amount.display}" for t in transfers
        )
    )
    return reply(
        text,
        v.SimplifiedDebtsResult(
            group_id=r["group_id"],
            group=r["group_name"],
            transfers=transfers,
            before_count=r["original_transfer_count"],
            after_count=len(transfers),
        ),
    )


# =========================================================================== TOOLS: write
class SplitParticipant(BaseModel):
    user_id: int = Field(
        description="Participant's user id (from resolve_person / get_group_details)"
    )
    value: str | float | None = Field(
        default=None,
        description=(
            'equal: omit. exact: this person\'s amount in currency units ("400.50"). '
            'percent: e.g. "33.33". shares: e.g. "2".'
        ),
    )


class SplitSpec(BaseModel):
    type: Literal["equal", "exact", "percent", "shares"] = Field(
        description="How to divide the amount"
    )
    participants: list[SplitParticipant] = Field(
        default_factory=list,
        description="Who shares the cost. For type=equal in a group you may leave this empty to mean ALL members.",
    )


async def _split_to_api(
    c: MyShareAPI, split: SplitSpec, currency: str, group_id: int | None, friend_id: int | None
) -> dict[str, Any]:
    participants = split.participants
    if not participants:
        if split.type != "equal":
            raise ToolError(f"A {split.type} split needs explicit participants with values.")
        if group_id is not None:
            members = (await c.get(f"/groups/{group_id}"))["members"]
            participants = [SplitParticipant(user_id=m["id"]) for m in members]
        elif friend_id is not None:
            me = (await c.get("/users/me"))["id"]
            participants = [SplitParticipant(user_id=me), SplitParticipant(user_id=friend_id)]
    out = []
    for p in participants:
        value: Any = p.value
        if split.type == "exact":
            if value is None:
                raise ToolError(f"Exact split: give an amount for user {p.user_id}.")
            value = _minor(
                value, currency, f"exact amount for user {p.user_id}"
            )  # API wants minor units
        elif value is not None:
            value = str(value)
        out.append({"user_id": p.user_id, "value": value})
    return {"type": split.type, "participants": out}


def _expense_summary(verb: str, done: str, e: v.ExpenseItem, preview: bool) -> str:
    """Previews read 'would add ...'; real results read 'Added ...'."""
    where = f' in "{e.group}"' if e.group else ""
    split = ", ".join(f"{s.name} {s.owes.display}" for s in e.split)
    action = f"PREVIEW (nothing saved): would {verb}" if preview else done
    return f'{action} "{e.description}" {e.amount.display}{where}, paid by {e.paid_by.name}; split {e.split_type}: {split}.'


@mcp.tool(title="Add an expense", annotations=WRITE)
async def add_expense(
    description: Annotated[
        str, Field(min_length=1, max_length=200, description='What it was for, e.g. "Dinner"')
    ],
    amount: Amount,
    split: SplitSpec,
    group_id: Annotated[int | None, Field(description="Group id, for a group expense")] = None,
    friend_id: Annotated[
        int | None, Field(description="Friend's user id, for a 1:1 non-group expense")
    ] = None,
    payer_id: Annotated[
        int | None, Field(description="Who paid (user id). Defaults to the current user.")
    ] = None,
    currency: Annotated[
        str | None, Field(description="ISO code; defaults to the group's currency")
    ] = None,
    date: Annotated[str | None, Field(description="YYYY-MM-DD; defaults to today")] = None,
    category: Annotated[
        str | None,
        Field(
            description="general, food, groceries, transport, lodging, travel, rent, utilities, entertainment, shopping, health, other"
        ),
    ] = None,
    dry_run: DryRun = False,
) -> Annotated[CallToolResult, v.ExpenseWriteResult]:
    """Record a shared expense. Provide EITHER group_id OR friend_id.

    Resolve people to ids first (resolve_person / get_group_details). Confirm the amount
    and currency with the user if they are unclear.
    """
    async with api() as c:
        cur = await _group_or_friend_currency(c, group_id, friend_id, currency)
        payer = payer_id if payer_id is not None else (await c.get("/users/me"))["id"]
        body = {
            "group_id": group_id,
            "friend_id": friend_id,
            "description": description,
            "amount": _minor(amount, cur),
            "currency": cur,
            "payer_id": payer,
            "split": await _split_to_api(c, split, cur, group_id, friend_id),
            "date": date,
            "category": category or "general",
        }
        e = v.expense_item(
            await c.post(
                "/expenses", {k: x for k, x in body.items() if x is not None}, dry_run=dry_run
            )
        )
    return reply(
        _expense_summary("add", "Added", e, dry_run),
        v.ExpenseWriteResult(action="created", preview=dry_run, expense=e),
    )


@mcp.tool(title="Edit an expense", annotations=WRITE_IDEMPOTENT)
async def update_expense(
    expense_id: Annotated[
        int, Field(description="Expense id from list_expenses / search_expenses")
    ],
    description: Annotated[str | None, Field(max_length=200)] = None,
    amount: Annotated[
        str | float | None, Field(description='New total in currency units, e.g. "1500"')
    ] = None,
    payer_id: Annotated[int | None, Field(description="New payer's user id")] = None,
    split: Annotated[SplitSpec | None, Field(description="Replace the whole split")] = None,
    date: Annotated[str | None, Field(description="YYYY-MM-DD")] = None,
    category: str | None = None,
    dry_run: DryRun = False,
) -> Annotated[CallToolResult, v.ExpenseWriteResult]:
    """Change fields of an existing expense. Only the fields you pass are changed.

    Changing only the amount keeps the existing split proportions.
    """
    async with api() as c:
        current = await c.get(f"/expenses/{expense_id}")
        cur = current["currency"]
        body: dict[str, Any] = {
            "description": description,
            "payer_id": payer_id,
            "date": date,
            "category": category,
        }
        if amount is not None:
            body["amount"] = _minor(amount, cur)
        if split is not None:
            body["split"] = await _split_to_api(c, split, cur, current["group_id"], None)
        e = v.expense_item(
            await c.patch(
                f"/expenses/{expense_id}",
                {k: x for k, x in body.items() if x is not None},
                dry_run=dry_run,
            )
        )
    return reply(
        _expense_summary("update", "Updated", e, dry_run),
        v.ExpenseWriteResult(action="updated", preview=dry_run, expense=e),
    )


@mcp.tool(title="Delete an expense", annotations=DESTRUCTIVE)
async def delete_expense(
    expense_id: Annotated[
        int, Field(description="Expense id from list_expenses / search_expenses")
    ],
    dry_run: DryRun = False,
) -> Annotated[CallToolResult, v.ExpenseWriteResult]:
    """Delete an expense (it stops counting toward balances; the activity log keeps a record).

    Make sure you have the right expense: if the user said "the last one", look it up first and
    mention its description and amount.
    """
    async with api() as c:
        e = v.expense_item(await c.delete(f"/expenses/{expense_id}", dry_run=dry_run))
    prefix = "PREVIEW (nothing saved): would delete" if dry_run else "Deleted"
    where = f' from "{e.group}"' if e.group else ""
    return reply(
        f'{prefix} "{e.description}" ({e.amount.display}, {e.date}){where}.',
        v.ExpenseWriteResult(action="deleted", preview=dry_run, expense=e),
    )


@mcp.tool(title="Record a payment", annotations=WRITE)
async def settle_up(
    from_user_id: Annotated[int, Field(description="Who paid the money (user id)")],
    to_user_id: Annotated[int, Field(description="Who received it (user id)")],
    amount: Amount,
    group_id: Annotated[
        int | None, Field(description="Record it inside this group (recommended for group debts)")
    ] = None,
    currency: str | None = None,
    note: Annotated[str | None, Field(max_length=200)] = None,
    dry_run: DryRun = False,
) -> Annotated[CallToolResult, v.SettlementResult]:
    """Record that one person paid another (e.g. "Rahul paid me back ₹500"). This does not move real money."""
    async with api() as c:
        cur = await _group_or_friend_currency(c, group_id, None, currency)
        s = await c.post(
            "/settlements",
            {
                k: x
                for k, x in {
                    "from_user_id": from_user_id,
                    "to_user_id": to_user_id,
                    "amount": _minor(amount, cur),
                    "currency": cur,
                    "group_id": group_id,
                    "note": note,
                }.items()
                if x is not None
            },
            dry_run=dry_run,
        )
    r = v.SettlementResult(
        preview=dry_run,
        id=None if dry_run else s["id"],
        from_person=v.person(s["from_user"]),
        to_person=v.person(s["to_user"]),
        amount=v.money(s["amount"], s["currency"]),
        group_id=s["group_id"],
        date=s["date"],
    )
    prefix = "PREVIEW (nothing saved): would record" if dry_run else "Recorded"
    return reply(f"{prefix}: {r.from_person.name} paid {r.to_person.name} {r.amount.display}.", r)


@mcp.tool(title="Create a group", annotations=WRITE)
async def create_group(
    name: Annotated[str, Field(min_length=1, max_length=100, description='e.g. "Goa Trip"')],
    member_emails: Annotated[
        list[str],
        Field(
            description="Emails of existing MyShare users to add (the current user is added automatically)"
        ),
    ],
    kind: Literal["trip", "home", "couple", "dinner", "other"] = "other",
    currency: str = "INR",
    dry_run: DryRun = False,
) -> Annotated[CallToolResult, v.GroupWriteResult]:
    """Create a new group with the current user and the given members."""
    async with api() as c:
        g = await c.post(
            "/groups",
            {
                "name": name,
                "member_emails": member_emails,
                "kind": kind,
                "currency": currency.upper(),
            },
            dry_run=dry_run,
        )
    d = _group_details(g)
    prefix = "PREVIEW (nothing saved): would create" if dry_run else "Created"
    return reply(
        f'{prefix} group "{d.name}" ({d.currency}) with '
        + ", ".join(m.name for m in d.members)
        + ".",
        v.GroupWriteResult(group=d, preview=dry_run),
    )


@mcp.tool(title="Add a friend", annotations=WRITE_IDEMPOTENT)
async def add_friend(
    email: Annotated[str, Field(description="The friend's MyShare account email")],
    dry_run: DryRun = False,
) -> Annotated[CallToolResult, v.FriendAddedResult]:
    """Add an existing MyShare user as a friend, by email."""
    async with api() as c:
        f = _friend(await c.post("/friends", {"email": email}, dry_run=dry_run))
    prefix = "PREVIEW (nothing saved): would add" if dry_run else "Added"
    return reply(
        f"{prefix} {f.name} ({f.email}) as a friend.",
        v.FriendAddedResult(friend=f, preview=dry_run),
    )


# =========================================================================== RESOURCES
# Resources are read by the HOST (application-controlled), not chosen by the model.
# Our host reads myshare://me/summary at the start of every turn and puts it in the
# system prompt, so the model always knows who "me" is without spending a tool call.
async def _resource_get(path: str, **params: Any) -> Any:
    """GET from the API for a resource read. Resources signal anticipated failures with
    ResourceError (tools use ToolError); either way the client gets a readable message."""
    try:
        async with api() as c:
            return await c.get(path, **params)
    except ToolError as exc:
        raise ResourceError(str(exc)) from None


def _int_id(raw: str) -> int:
    try:
        return int(raw)
    except ValueError:
        raise ResourceError(f"'{raw}' is not a valid group id (expected a number).") from None


@mcp.resource(
    "myshare://me/summary",
    name="my_summary",
    title="My profile & overall balance",
    description="The current user's id, name, email, and how much they owe / are owed overall.",
    mime_type="application/json",
)
async def me_summary() -> str:
    s = await _resource_get("/users/me/summary")
    data = {
        "user": s["user"],
        "default_currency": s["default_currency"],
        "balances": [
            {
                "currency": b["currency"],
                "owed_to_you": v.money(b["owed_to_you"], b["currency"]).display,
                "you_owe": v.money(b["you_owe"], b["currency"]).display,
                "net": v.money(b["net"], b["currency"]).display,
            }
            for b in s["balances"]
        ],
        "friend_count": s["friend_count"],
        "group_count": s["group_count"],
        "today": dt.date.today().isoformat(),
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


@mcp.resource(
    "myshare://groups/{group_id}",
    name="group_snapshot",
    title="Group snapshot",
    description="Members, balances and recent expenses of one group.",
    mime_type="application/json",
)
async def group_snapshot(group_id: str) -> str:
    g = await _resource_get(f"/groups/{_int_id(group_id)}")
    recent = await _resource_get("/expenses", group_id=_int_id(group_id), limit=10)
    return _group_details(g, recent).model_dump_json(indent=2)


@mcp.resource(
    "myshare://groups/{group_id}/activity",
    name="group_activity",
    title="Group activity feed",
    description="The 30 most recent activity entries in a group.",
    mime_type="application/json",
)
async def group_activity(group_id: str) -> str:
    rows = await _resource_get("/activity", group_id=_int_id(group_id), limit=30)
    return json.dumps(
        [{"when": a["created_at"], "who": a["actor"]["name"], "what": a["summary"]} for a in rows],
        ensure_ascii=False,
        indent=2,
    )


# =========================================================================== PROMPTS
# Prompts are templates the USER invokes (our chat UI shows them as /slash-commands).
# They return messages that seed the conversation; the model then uses tools as usual.
@mcp.prompt(title="Plan to settle a group")
def settle_up_plan(group_id: Annotated[str, Field(description="Group id")]) -> list[Message]:
    """Create a plan for settling this group's debts with the fewest payments."""
    return [
        UserMessage(
            f"Create a plan for settling the debts in group {group_id}.\n"
            "1. Call get_group_details to see members and balances.\n"
            "2. Call get_simplified_debts to get the minimum set of payments.\n"
            "3. Present the plan as a short numbered list: who pays whom and how much.\n"
            "4. Point out which payments involve me, and offer to record them with settle_up "
            "(only after I confirm each one)."
        )
    ]


@mcp.prompt(title="Monthly spending summary")
def monthly_summary(
    month: Annotated[str, Field(description="Month as YYYY-MM, e.g. 2026-09")],
) -> list[Message]:
    """Summarize my spending for a month: totals, categories, and who I owe."""
    try:
        start = dt.date.fromisoformat(f"{month}-01")
    except ValueError:
        start = dt.date.today().replace(day=1)
    end = (start.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
    return [
        UserMessage(
            f"Summarize my MyShare spending for {start:%B %Y}.\n"
            f"Call list_expenses with since={start.isoformat()}, until={end.isoformat()} and limit=50.\n"
            "Report: (a) total of MY share across all expenses (sum of what I owe on each), "
            "(b) a breakdown by category, (c) the 3 biggest expenses, "
            "and (d) my current overall balance (get_balances). Keep it brief and use a small table."
        )
    ]


@mcp.prompt(title="Split a receipt")
def split_receipt(
    description: Annotated[
        str, Field(description="What the receipt is for, e.g. 'Dinner at Thalassa ₹4,200'")
    ],
) -> list[Message]:
    """Guided expense entry: I'll ask you the right questions, then add the expense."""
    return [
        UserMessage(f"I want to split a receipt: {description}"),
        AssistantMessage(
            "Let's get this right. I need to know:\n"
            "1. The total amount (and currency, if not the group's).\n"
            "2. Which group it belongs to, or which friend it's with.\n"
            "3. Who paid.\n"
            "4. How to split it: equally, exact amounts, percentages, or shares.\n"
            "Tell me what you know and I'll look up the rest."
        ),
    ]
