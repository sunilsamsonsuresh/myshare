"""SQLAlchemy 2.x models.

Design rule: balances are NEVER stored. They are derived from expenses (+ splits)
and settlements every time (see services/balances.py). A stored balance can drift
out of sync with the rows that justify it; a derived one cannot.

All money columns are integers in minor units (paise/cents).
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import JSON, Date, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, UTCDateTime


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255))
    default_currency: Mapped[str] = mapped_column(String(3), default="INR")
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=_now)


class Friendship(Base):
    """Directed edge; we always write both directions so 'my friends' is one query.

    (Not in the original model list: friends need to be stored somewhere.)
    """

    __tablename__ = "friendships"
    __table_args__ = (UniqueConstraint("user_id", "friend_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    friend_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=_now)


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(
        String(20), default="other"
    )  # trip | home | couple | dinner | other
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=_now)

    members: Mapped[list[GroupMember]] = relationship(
        back_populates="group", cascade="all, delete-orphan", order_by="GroupMember.id"
    )


class GroupMember(Base):
    __tablename__ = "group_members"
    __table_args__ = (UniqueConstraint("group_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    joined_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=_now)

    group: Mapped[Group] = relationship(back_populates="members")
    user: Mapped[User] = relationship()


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    # NULL group_id = a non-group expense between friends.
    group_id: Mapped[int | None] = mapped_column(ForeignKey("groups.id"), index=True)
    description: Mapped[str] = mapped_column(String(200))
    amount: Mapped[int] = mapped_column(Integer)  # minor units
    currency: Mapped[str] = mapped_column(String(3))
    date: Mapped[dt.date] = mapped_column(Date)
    category: Mapped[str] = mapped_column(String(30), default="general")
    payer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    split_type: Mapped[str] = mapped_column(String(10))  # equal | exact | percent | shares
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=_now, onupdate=_now)
    deleted_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime())  # soft delete

    splits: Mapped[list[ExpenseSplit]] = relationship(
        back_populates="expense", cascade="all, delete-orphan", order_by="ExpenseSplit.id"
    )
    payer: Mapped[User] = relationship(foreign_keys=[payer_id])
    group: Mapped[Group | None] = relationship()


class ExpenseSplit(Base):
    __tablename__ = "expense_splits"

    id: Mapped[int] = mapped_column(primary_key=True)
    expense_id: Mapped[int] = mapped_column(
        ForeignKey("expenses.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    owed_amount: Mapped[int] = mapped_column(Integer)  # minor units this user owes for the expense
    # The raw input that produced owed_amount (exact minor units, a percent, or a share count),
    # kept so the edit form can show what the user originally typed.
    share_value: Mapped[str | None] = mapped_column(String(32))

    expense: Mapped[Expense] = relationship(back_populates="splits")
    user: Mapped[User] = relationship()


class Settlement(Base):
    """A real-world payment: from_user paid to_user `amount`."""

    __tablename__ = "settlements"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("groups.id"), index=True)
    from_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    to_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    amount: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    date: Mapped[dt.date] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(String(200))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=_now)
    deleted_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime())

    from_user: Mapped[User] = relationship(foreign_keys=[from_user_id])
    to_user: Mapped[User] = relationship(foreign_keys=[to_user_id])


class Activity(Base):
    """Append-only log. `summary` is a ready-to-show sentence; `data` holds details."""

    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    verb: Mapped[str] = mapped_column(String(30))
    group_id: Mapped[int | None] = mapped_column(ForeignKey("groups.id"), index=True)
    expense_id: Mapped[int | None] = mapped_column(ForeignKey("expenses.id"))
    settlement_id: Mapped[int | None] = mapped_column(ForeignKey("settlements.id"))
    summary: Mapped[str] = mapped_column(String(300))
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=_now, index=True)

    actor: Mapped[User] = relationship()
    audience: Mapped[list[ActivityAudience]] = relationship(cascade="all, delete-orphan")


class ActivityAudience(Base):
    """Who may see an activity row (the people involved), so the feed is a simple join."""

    __tablename__ = "activity_audience"
    __table_args__ = (UniqueConstraint("activity_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)


__all__ = [
    "Activity",
    "ActivityAudience",
    "Base",
    "Expense",
    "ExpenseSplit",
    "Friendship",
    "Group",
    "GroupMember",
    "Settlement",
    "User",
    "func",
]
