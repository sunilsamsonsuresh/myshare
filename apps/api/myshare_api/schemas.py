"""Pydantic v2 request/response models. All money fields are integer minor units."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from myshare_shared.money import SUPPORTED_CURRENCIES

from .services.splits import SplitType

CATEGORIES = (
    "general",
    "food",
    "groceries",
    "transport",
    "lodging",
    "travel",
    "rent",
    "utilities",
    "entertainment",
    "shopping",
    "health",
    "other",
)
GROUP_KINDS = ("trip", "home", "couple", "dinner", "other")


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def _category(v: str) -> str:
    v = v.lower()
    if v not in CATEGORIES:
        raise ValueError(f"Unknown category '{v}'. Use one of: {', '.join(CATEGORIES)}")
    return v


def _currency(v: str) -> str:
    v = v.upper()
    if v not in SUPPORTED_CURRENCIES:
        raise ValueError(
            f"Unsupported currency '{v}'. Supported: {', '.join(SUPPORTED_CURRENCIES)}"
        )
    return v


# ---------- users / auth ----------
class UserOut(ORM):
    id: int
    email: str
    name: str


class SignupIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserOut


class Money(BaseModel):
    currency: str
    amount: int  # signed minor units: >0 owed to you, <0 you owe


class OverallBalanceOut(BaseModel):
    currency: str
    owed_to_you: int
    you_owe: int
    net: int


class SummaryOut(BaseModel):
    user: UserOut
    default_currency: str
    balances: list[OverallBalanceOut]
    friend_count: int
    group_count: int


# ---------- friends ----------
class FriendAddIn(BaseModel):
    email: EmailStr


class FriendOut(UserOut):
    balances: list[Money] = []


class FriendGroupBalance(BaseModel):
    group_id: int | None
    group_name: str
    balances: list[Money]


class FriendDetailOut(FriendOut):
    breakdown: list[FriendGroupBalance]


class PersonMatch(UserOut):
    via: str  # "you" | "friend" | "group: Goa Trip"


class ResolveOut(BaseModel):
    query: str
    matches: list[PersonMatch]


# ---------- groups ----------
class GroupCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    kind: Literal["trip", "home", "couple", "dinner", "other"] = "other"
    currency: str = "INR"
    member_emails: list[EmailStr] = []

    @field_validator("currency")
    @classmethod
    def _cur(cls, v: str) -> str:
        return _currency(v)


class GroupUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    kind: Literal["trip", "home", "couple", "dinner", "other"] | None = None


class MemberAddIn(BaseModel):
    email: EmailStr


class GroupMemberOut(UserOut):
    balance: int  # net in group currency


class GroupOut(BaseModel):
    id: int
    name: str
    kind: str
    currency: str
    created_at: dt.datetime
    member_count: int
    my_balance: int


class GroupDetailOut(GroupOut):
    members: list[GroupMemberOut]
    total_spent: int
    expense_count: int


class TransferOut(BaseModel):
    from_user: UserOut
    to_user: UserOut
    amount: int


class SimplifiedDebtsOut(BaseModel):
    group_id: int
    group_name: str
    currency: str
    transfers: list[TransferOut]
    original_transfer_count: int  # how many pairwise debts existed before simplifying


# ---------- expenses ----------
class SplitParticipantIn(BaseModel):
    user_id: int
    # equal: omit · exact: minor units · percent: "33.33" · shares: "2"
    value: Decimal | None = None


class SplitIn(BaseModel):
    type: SplitType
    participants: list[SplitParticipantIn] = Field(min_length=1)


class ExpenseCreateIn(BaseModel):
    group_id: int | None = None
    friend_id: int | None = None
    description: str = Field(min_length=1, max_length=200)
    amount: int = Field(gt=0, description="Minor units (paise/cents)")
    currency: str | None = None  # defaults to group currency / user default
    date: dt.date | None = None
    category: str = "general"
    payer_id: int
    split: SplitIn

    @field_validator("category")
    @classmethod
    def _cat(cls, v: str) -> str:
        return _category(v)

    @field_validator("currency")
    @classmethod
    def _cur(cls, v: str | None) -> str | None:
        return None if v is None else _currency(v)


class ExpenseUpdateIn(BaseModel):
    description: str | None = Field(default=None, min_length=1, max_length=200)
    amount: int | None = Field(default=None, gt=0)
    date: dt.date | None = None
    category: str | None = None
    payer_id: int | None = None
    split: SplitIn | None = None

    @field_validator("category")
    @classmethod
    def _cat(cls, v: str | None) -> str | None:
        return None if v is None else _category(v)


class SplitOut(BaseModel):
    user: UserOut
    owed_amount: int
    share_value: str | None


class ExpenseOut(BaseModel):
    id: int
    group_id: int | None
    group_name: str | None
    description: str
    amount: int
    currency: str
    date: dt.date
    category: str
    payer: UserOut
    split_type: str
    splits: list[SplitOut]
    created_by: int
    created_at: dt.datetime
    updated_at: dt.datetime
    my_net: int  # effect on the caller: paid - owed (>0 you lent, <0 you borrowed)


# ---------- settlements ----------
class SettlementCreateIn(BaseModel):
    from_user_id: int
    to_user_id: int
    amount: int = Field(gt=0)
    currency: str | None = None
    group_id: int | None = None
    date: dt.date | None = None
    note: str | None = Field(default=None, max_length=200)

    @field_validator("currency")
    @classmethod
    def _cur(cls, v: str | None) -> str | None:
        return None if v is None else _currency(v)


class SettlementOut(BaseModel):
    id: int
    group_id: int | None
    from_user: UserOut
    to_user: UserOut
    amount: int
    currency: str
    date: dt.date
    note: str | None
    created_at: dt.datetime


# ---------- balances / activity ----------
class BalancesOut(BaseModel):
    scope: Literal["overall", "friend", "group"]
    # overall: per currency totals
    overall: list[OverallBalanceOut] | None = None
    # friend: net with that friend (+breakdown)
    friend: FriendDetailOut | None = None
    # group: every member's net in the group
    group: GroupDetailOut | None = None


class ActivityOut(BaseModel):
    id: int
    verb: str
    summary: str
    actor: UserOut
    group_id: int | None
    expense_id: int | None
    settlement_id: int | None
    data: dict[str, Any]
    created_at: dt.datetime
