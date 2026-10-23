"""Derive balances from expenses + settlements. Nothing here is stored.

Sign convention everywhere: positive = "is owed money", negative = "owes money".

Pairwise ledger: for every expense split where user U owes `owed` and P paid,
U owes P `owed` (unless U == P). A settlement where A paid B `x` reduces what
A owes B by x. From the pairwise ledger we can answer every balance question.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from ..models import Expense, ExpenseSplit, Settlement


@dataclass
class Ledger:
    """debts[(debtor, creditor, currency)] = minor units the debtor owes the creditor (pre-netting)."""

    debts: dict[tuple[int, int, str], int] = field(default_factory=lambda: defaultdict(int))

    def add(self, debtor: int, creditor: int, currency: str, amount: int) -> None:
        if debtor != creditor and amount:
            self.debts[(debtor, creditor, currency)] += amount

    def between(self, me: int, other: int) -> dict[str, int]:
        """Net per currency from `me`'s point of view: >0 other owes me, <0 I owe other."""
        out: dict[str, int] = defaultdict(int)
        for (d, c, cur), amt in self.debts.items():
            if d == other and c == me:
                out[cur] += amt
            elif d == me and c == other:
                out[cur] -= amt
        return {cur: v for cur, v in out.items() if v}

    def nets(self) -> dict[str, dict[int, int]]:
        """Net balance per currency per user."""
        out: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
        for (d, c, cur), amt in self.debts.items():
            out[cur][d] -= amt
            out[cur][c] += amt
        return {cur: dict(v) for cur, v in out.items()}

    def counterparties(self, me: int) -> set[int]:
        return {c if d == me else d for (d, c, _) in self.debts if me in (d, c)}


def build_ledger(expenses: Iterable[Expense], settlements: Iterable[Settlement]) -> Ledger:
    ledger = Ledger()
    for e in expenses:
        if e.deleted_at is not None:
            continue
        for s in e.splits:
            ledger.add(s.user_id, e.payer_id, e.currency, s.owed_amount)
    for st in settlements:
        if st.deleted_at is not None:
            continue
        # from_user paid to_user: equivalent to to_user now owing from_user that amount.
        ledger.add(st.to_user_id, st.from_user_id, st.currency, st.amount)
    return ledger


def group_ledger(db: Session, group_id: int) -> Ledger:
    expenses = db.scalars(
        select(Expense)
        .where(Expense.group_id == group_id, Expense.deleted_at.is_(None))
        .options(selectinload(Expense.splits))
    ).all()
    settlements = db.scalars(
        select(Settlement).where(Settlement.group_id == group_id, Settlement.deleted_at.is_(None))
    ).all()
    return build_ledger(expenses, settlements)


def user_ledger(db: Session, user_id: int) -> Ledger:
    """Every expense/settlement (any group or none) that involves `user_id`."""
    involved = select(ExpenseSplit.expense_id).where(ExpenseSplit.user_id == user_id)
    expenses = db.scalars(
        select(Expense)
        .where(
            Expense.deleted_at.is_(None), or_(Expense.payer_id == user_id, Expense.id.in_(involved))
        )
        .options(selectinload(Expense.splits))
    ).all()
    settlements = db.scalars(
        select(Settlement).where(
            Settlement.deleted_at.is_(None),
            or_(Settlement.from_user_id == user_id, Settlement.to_user_id == user_id),
        )
    ).all()
    return build_ledger(expenses, settlements)


@dataclass
class OverallBalance:
    currency: str
    owed_to_you: int  # sum of positive per-friend balances
    you_owe: int  # sum of negative per-friend balances, as a positive number
    net: int


def overall_for(ledger: Ledger, me: int) -> list[OverallBalance]:
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for other in ledger.counterparties(me):
        for cur, v in ledger.between(me, other).items():
            totals[cur][0 if v > 0 else 1] += abs(v)
    return [
        OverallBalance(cur, owed, owe, owed - owe) for cur, (owed, owe) in sorted(totals.items())
    ]
