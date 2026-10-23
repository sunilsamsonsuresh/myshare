"""Business rules shared by several routers: friendships, activity log, serialization."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from fastapi import HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from myshare_shared.money import format_money

from ..models import (
    Activity,
    ActivityAudience,
    Expense,
    Friendship,
    Group,
    GroupMember,
    Settlement,
    User,
)
from ..schemas import (
    ExpenseOut,
    GroupDetailOut,
    GroupMemberOut,
    GroupOut,
    SettlementOut,
    SplitOut,
    UserOut,
)
from .balances import group_ledger

# `?dry_run=true` on write endpoints: run every validation and build the response,
# then roll back instead of committing. The MCP host uses it to render an accurate
# approval card ("this is exactly what will happen") before the user approves.
DryRun = Query(False, description="Validate and preview the result without saving anything")


def finish(db: Session, dry_run: bool) -> None:
    db.rollback() if dry_run else db.commit()


def user_out(u: User) -> UserOut:
    return UserOut(id=u.id, email=u.email, name=u.name)


def make_friends(db: Session, a: int, b: int) -> bool:
    """Create the friendship in both directions. Returns True if it was new."""
    if a == b:
        return False
    existing = db.scalar(
        select(Friendship.id).where(Friendship.user_id == a, Friendship.friend_id == b)
    )
    if existing:
        return False
    db.add_all([Friendship(user_id=a, friend_id=b), Friendship(user_id=b, friend_id=a)])
    return True


def friend_ids(db: Session, user_id: int) -> set[int]:
    return set(db.scalars(select(Friendship.friend_id).where(Friendship.user_id == user_id)))


def member_ids(db: Session, group_id: int) -> list[int]:
    return list(
        db.scalars(
            select(GroupMember.user_id)
            .where(GroupMember.group_id == group_id)
            .order_by(GroupMember.id)
        )
    )


def log_activity(
    db: Session,
    *,
    actor: User,
    verb: str,
    summary: str,
    audience: Iterable[int],
    group_id: int | None = None,
    expense_id: int | None = None,
    settlement_id: int | None = None,
    data: dict[str, Any] | None = None,
) -> Activity:
    act = Activity(
        actor_id=actor.id,
        verb=verb,
        summary=summary,
        group_id=group_id,
        expense_id=expense_id,
        settlement_id=settlement_id,
        data=data or {},
    )
    act.audience = [ActivityAudience(user_id=uid) for uid in sorted(set(audience) | {actor.id})]
    db.add(act)
    return act


def money(minor: int, currency: str) -> str:
    return format_money(minor, currency)


def get_user_or_404(db: Session, user_id: int, role: str = "User") -> User:
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(404, f"{role} with id {user_id} does not exist.")
    return u


# ---------- serialization ----------
def expense_out(e: Expense, me: int) -> ExpenseOut:
    my_owed = sum(s.owed_amount for s in e.splits if s.user_id == me)
    my_paid = e.amount if e.payer_id == me else 0
    return ExpenseOut(
        id=e.id,
        group_id=e.group_id,
        group_name=e.group.name if e.group else None,
        description=e.description,
        amount=e.amount,
        currency=e.currency,
        date=e.date,
        category=e.category,
        payer=user_out(e.payer),
        split_type=e.split_type,
        splits=[
            SplitOut(user=user_out(s.user), owed_amount=s.owed_amount, share_value=s.share_value)
            for s in e.splits
        ],
        created_by=e.created_by,
        created_at=e.created_at,
        updated_at=e.updated_at,
        my_net=my_paid - my_owed,
    )


def settlement_out(s: Settlement) -> SettlementOut:
    return SettlementOut(
        id=s.id,
        group_id=s.group_id,
        from_user=user_out(s.from_user),
        to_user=user_out(s.to_user),
        amount=s.amount,
        currency=s.currency,
        date=s.date,
        note=s.note,
        created_at=s.created_at,
    )


def group_out(db: Session, g: Group, me: int) -> GroupOut:
    nets = group_ledger(db, g.id).nets().get(g.currency, {})
    return GroupOut(
        id=g.id,
        name=g.name,
        kind=g.kind,
        currency=g.currency,
        created_at=g.created_at,
        member_count=len(g.members),
        my_balance=nets.get(me, 0),
    )


def group_detail_out(db: Session, g: Group, me: int) -> GroupDetailOut:
    nets = group_ledger(db, g.id).nets().get(g.currency, {})
    expenses = db.scalars(
        select(Expense).where(Expense.group_id == g.id, Expense.deleted_at.is_(None))
    ).all()
    return GroupDetailOut(
        **group_out(db, g, me).model_dump(),
        members=[
            GroupMemberOut(
                id=m.user.id, email=m.user.email, name=m.user.name, balance=nets.get(m.user_id, 0)
            )
            for m in g.members
        ],
        total_spent=sum(e.amount for e in expenses),
        expense_count=len(expenses),
    )
