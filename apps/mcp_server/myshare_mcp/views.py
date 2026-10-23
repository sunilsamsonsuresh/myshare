"""Output models: the shape of data this MCP server hands to the model.

Why not just return the REST API's JSON?

1. Money: the API speaks integer minor units (120050). An LLM reading "120050"
   will sometimes say "₹1,20,050". At the MCP boundary we present money as a
   decimal string plus currency plus a display string, so there's nothing to
   misread: {"amount": "1200.50", "currency": "INR", "display": "₹1,200.50"}.
2. Size: tool results go into the model's context window. We keep only the
   fields that help the model answer or act (ids, names, amounts), not
   timestamps or internal flags.
3. Clarity: we add derived hints such as `status: "owes you"`, so the model
   doesn't have to reason about sign conventions.

Each model doubles as the tool's published `outputSchema` (structured content),
so clients can validate and render results without parsing text.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from myshare_shared.money import format_money, to_decimal_str


class Money(BaseModel):
    amount: str  # decimal string, e.g. "1200.50" (negative = you owe)
    currency: str
    display: str  # "₹1,200.50"


def money(minor: int, currency: str) -> Money:
    return Money(
        amount=to_decimal_str(minor, currency),
        currency=currency,
        display=format_money(minor, currency),
    )


def status_of(minor: int) -> str:
    return "owes you" if minor > 0 else "you owe" if minor < 0 else "settled up"


class Person(BaseModel):
    id: int
    name: str
    email: str


def person(u: dict[str, Any]) -> Person:
    return Person(id=u["id"], name=u["name"], email=u["email"])


# ---------- people ----------
class PersonMatch(Person):
    via: str


class ResolvePersonResult(BaseModel):
    query: str
    status: Literal["unique", "ambiguous", "not_found"]
    matches: list[PersonMatch]
    hint: str


class FriendBalance(Person):
    balances: list[Money]
    status: str  # "owes you" / "you owe" / "settled up" (first currency)


class FriendsResult(BaseModel):
    friends: list[FriendBalance]


class FriendAddedResult(BaseModel):
    friend: FriendBalance
    preview: bool


# ---------- groups ----------
class GroupSummary(BaseModel):
    id: int
    name: str
    kind: str
    currency: str
    member_count: int
    your_balance: Money
    status: str


class GroupsResult(BaseModel):
    groups: list[GroupSummary]


class Member(Person):
    balance: Money
    status: str


class GroupDetails(BaseModel):
    id: int
    name: str
    kind: str
    currency: str
    members: list[Member]
    total_spent: Money
    expense_count: int
    your_balance: Money
    recent_expenses: list[ExpenseItem] = []


class GroupWriteResult(BaseModel):
    group: GroupDetails
    preview: bool


# ---------- expenses ----------
class SplitLine(BaseModel):
    person_id: int
    name: str
    owes: Money
    input: str | None = None  # the raw share/percent/exact value the split was computed from


class ExpenseItem(BaseModel):
    id: int
    description: str
    amount: Money
    date: str
    category: str
    group: str | None = None
    group_id: int | None = None
    paid_by: Person
    split_type: str
    split: list[SplitLine]
    your_net: Money  # >0 you lent, <0 you borrowed


class ExpensesResult(BaseModel):
    expenses: list[ExpenseItem]
    count: int
    note: str | None = None


class ExpenseWriteResult(BaseModel):
    action: Literal["created", "updated", "deleted"]
    preview: bool  # True for dry runs: nothing was saved
    expense: ExpenseItem


def expense_item(e: dict[str, Any]) -> ExpenseItem:
    cur = e["currency"]
    return ExpenseItem(
        id=e["id"],
        description=e["description"],
        amount=money(e["amount"], cur),
        date=e["date"],
        category=e["category"],
        group=e["group_name"],
        group_id=e["group_id"],
        paid_by=person(e["payer"]),
        split_type=e["split_type"],
        split=[
            SplitLine(
                person_id=s["user"]["id"],
                name=s["user"]["name"],
                owes=money(s["owed_amount"], cur),
                input=s["share_value"],
            )
            for s in e["splits"]
        ],
        your_net=money(e["my_net"], cur),
    )


# ---------- balances / settle ----------
class OverallLine(BaseModel):
    currency: str
    owed_to_you: Money
    you_owe: Money
    net: Money


class FriendGroupLine(BaseModel):
    group_id: int | None = None
    group: str
    balances: list[Money]


class BalancesResult(BaseModel):
    scope: Literal["overall", "friend", "group"]
    overall: list[OverallLine] | None = None
    friend: FriendBalance | None = None
    friend_breakdown: list[FriendGroupLine] | None = None
    group: GroupDetails | None = None


class Transfer(BaseModel):
    from_person: Person
    to_person: Person
    amount: Money


class SimplifiedDebtsResult(BaseModel):
    group_id: int
    group: str
    transfers: list[Transfer]
    before_count: int  # pairwise debts before simplifying
    after_count: int


class SettlementResult(BaseModel):
    preview: bool
    id: int | None = None
    from_person: Person
    to_person: Person
    amount: Money
    group_id: int | None = None
    date: str


GroupDetails.model_rebuild()
