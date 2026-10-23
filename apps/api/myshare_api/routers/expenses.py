import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..deps import get_current_user, require_group_member
from ..models import Expense, ExpenseSplit, GroupMember, User
from ..schemas import ExpenseCreateIn, ExpenseOut, ExpenseUpdateIn, SplitIn
from ..services.common import (
    DryRun,
    expense_out,
    finish,
    friend_ids,
    get_user_or_404,
    log_activity,
    member_ids,
    money,
)
from ..services.splits import Participant, SplitError, compute_split

router = APIRouter(prefix="/expenses", tags=["expenses"])

_LOAD = (
    selectinload(Expense.splits).selectinload(ExpenseSplit.user),
    selectinload(Expense.payer),
    selectinload(Expense.group),
)


def _names(db: Session, ids: list[int]) -> str:
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(ids)))}
    return ", ".join(f"{users[i].name} (id {i})" for i in ids if i in users)


def _context_for(
    db: Session, user: User, group_id: int | None, friend_id: int | None
) -> tuple[list[int], str, str]:
    """Return (allowed participant ids, default currency, label) for a new expense."""
    if (group_id is None) == (friend_id is None):
        raise HTTPException(
            422,
            "Provide exactly one of group_id (a group expense) or friend_id (a 1:1 expense with a friend).",
        )
    if group_id is not None:
        group = require_group_member(db, group_id, user)
        return member_ids(db, group.id), group.currency, f'"{group.name}"'
    assert friend_id is not None
    if friend_id not in friend_ids(db, user.id):
        raise HTTPException(
            404, f"User {friend_id} is not one of your friends. Add them as a friend first."
        )
    friend = get_user_or_404(db, friend_id)
    return [user.id, friend_id], user.default_currency, f"with {friend.name}"


def _check_people(
    db: Session, allowed: list[int], payer_id: int, split: SplitIn, label: str
) -> None:
    if payer_id not in allowed:
        raise HTTPException(
            422,
            f"The payer (user id {payer_id}) isn't part of {label}. Allowed people are: {_names(db, allowed)}.",
        )
    outsiders = [p.user_id for p in split.participants if p.user_id not in allowed]
    if outsiders:
        raise HTTPException(
            422,
            f"User ids {outsiders} aren't part of {label}, so they can't be in the split. "
            f"Allowed people are: {_names(db, allowed)}.",
        )


def _apply_split(e: Expense, split: SplitIn) -> None:
    participants = [Participant(p.user_id, p.value) for p in split.participants]
    try:
        owed = compute_split(e.amount, split.type, participants)
    except SplitError as exc:
        raise HTTPException(422, str(exc)) from None
    raw = {p.user_id: p.value for p in split.participants}
    e.split_type = split.type.value
    e.splits.clear()
    e.splits.extend(
        ExpenseSplit(
            user_id=uid, owed_amount=amt, share_value=None if raw[uid] is None else str(raw[uid])
        )
        for uid, amt in owed.items()
    )


def _load_visible(db: Session, expense_id: int, user: User) -> Expense:
    e = db.scalar(
        select(Expense)
        .where(Expense.id == expense_id, Expense.deleted_at.is_(None))
        .options(*_LOAD)
    )
    if e is None or not _can_see(db, e, user):
        raise HTTPException(
            404,
            f"Expense {expense_id} not found (it may have been deleted, or isn't visible to you).",
        )
    return e


def _can_see(db: Session, e: Expense, user: User) -> bool:
    if e.group_id is not None:
        return user.id in member_ids(db, e.group_id)
    return user.id == e.payer_id or any(s.user_id == user.id for s in e.splits)


def _audience(db: Session, e: Expense) -> list[int]:
    if e.group_id is not None:
        return member_ids(db, e.group_id)
    return [e.payer_id, *(s.user_id for s in e.splits)]


@router.post("", response_model=ExpenseOut, status_code=201)
def create_expense(
    body: ExpenseCreateIn,
    dry_run: bool = DryRun,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExpenseOut:
    allowed, default_currency, label = _context_for(db, user, body.group_id, body.friend_id)
    currency = body.currency or default_currency
    if body.group_id is not None and currency != default_currency:
        raise HTTPException(
            422, f"{label} uses {default_currency}; all its expenses must be in {default_currency}."
        )
    _check_people(db, allowed, body.payer_id, body.split, label)

    e = Expense(
        group_id=body.group_id,
        description=body.description.strip(),
        amount=body.amount,
        currency=currency,
        date=body.date or dt.date.today(),
        category=body.category,
        payer_id=body.payer_id,
        split_type=body.split.type.value,
        created_by=user.id,
    )
    _apply_split(e, body.split)
    db.add(e)
    db.flush()
    payer = get_user_or_404(db, body.payer_id)
    log_activity(
        db,
        actor=user,
        verb="expense_added",
        summary=f'{user.name} added "{e.description}" ({money(e.amount, currency)}, paid by {payer.name}) {"in " if body.group_id else ""}{label}',
        audience=_audience(db, e),
        group_id=e.group_id,
        expense_id=e.id,
        data={"amount": e.amount, "currency": currency},
    )
    out = expense_out(_load_visible(db, e.id, user), user.id)
    finish(db, dry_run)
    return out


@router.get("", response_model=list[ExpenseOut])
def list_expenses(
    group_id: int | None = None,
    friend_id: int | None = None,
    since: dt.date | None = Query(None, description="Only expenses dated on/after this day"),
    until: dt.date | None = Query(None, description="Only expenses dated on/before this day"),
    q: str | None = Query(None, description="Case-insensitive text search in the description"),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ExpenseOut]:
    stmt = select(Expense).where(Expense.deleted_at.is_(None)).options(*_LOAD)
    involved = select(ExpenseSplit.expense_id).where(ExpenseSplit.user_id == user.id)
    if group_id is not None:
        require_group_member(db, group_id, user)
        stmt = stmt.where(Expense.group_id == group_id)
    else:
        my_groups = select(GroupMember.group_id).where(GroupMember.user_id == user.id)
        stmt = stmt.where(
            or_(
                Expense.payer_id == user.id,
                Expense.id.in_(involved),
                Expense.group_id.in_(my_groups),
            )
        )
    if friend_id is not None:
        if friend_id not in friend_ids(db, user.id):
            raise HTTPException(404, f"User {friend_id} is not one of your friends.")
        friend_in = select(ExpenseSplit.expense_id).where(ExpenseSplit.user_id == friend_id)
        stmt = stmt.where(
            or_(Expense.payer_id == user.id, Expense.id.in_(involved)),
            or_(Expense.payer_id == friend_id, Expense.id.in_(friend_in)),
        )
    if since is not None:
        stmt = stmt.where(Expense.date >= since)
    if until is not None:
        stmt = stmt.where(Expense.date <= until)
    if q:
        stmt = stmt.where(Expense.description.ilike(f"%{q.strip()}%"))
    stmt = stmt.order_by(Expense.date.desc(), Expense.id.desc()).limit(limit)
    return [expense_out(e, user.id) for e in db.scalars(stmt)]


@router.get("/{expense_id}", response_model=ExpenseOut)
def get_expense(
    expense_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> ExpenseOut:
    return expense_out(_load_visible(db, expense_id, user), user.id)


@router.patch("/{expense_id}", response_model=ExpenseOut)
def update_expense(
    expense_id: int,
    body: ExpenseUpdateIn,
    dry_run: bool = DryRun,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExpenseOut:
    e = _load_visible(db, expense_id, user)
    allowed = (
        member_ids(db, e.group_id) if e.group_id else [e.payer_id, *(s.user_id for s in e.splits)]
    )
    label = f'"{e.group.name}"' if e.group else "this expense"
    changes: dict[str, list] = {}

    for field in ("description", "date", "category"):
        new = getattr(body, field)
        if new is not None and new != getattr(e, field):
            changes[field] = [str(getattr(e, field)), str(new)]
            setattr(e, field, new)

    payer_id = body.payer_id if body.payer_id is not None else e.payer_id
    # Re-use the stored split when only the amount changes (re-computed for the new total).
    split = body.split or SplitIn(
        type=e.split_type,  # type: ignore[arg-type]
        participants=[{"user_id": s.user_id, "value": s.share_value} for s in e.splits],  # type: ignore[list-item]
    )
    _check_people(db, allowed, payer_id, split, label)
    if payer_id != e.payer_id:
        changes["payer_id"] = [e.payer_id, payer_id]
        e.payer_id = payer_id
    if body.amount is not None and body.amount != e.amount:
        changes["amount"] = [e.amount, body.amount]
        e.amount = body.amount
    if body.split is not None or "amount" in changes:
        before = {s.user_id: s.owed_amount for s in e.splits}
        _apply_split(e, split)
        after = {s.user_id: s.owed_amount for s in e.splits}
        if before != after:
            changes["split"] = [before, after]

    if not changes:
        return expense_out(e, user.id)
    log_activity(
        db,
        actor=user,
        verb="expense_updated",
        summary=f'{user.name} updated "{e.description}" ({", ".join(changes)})',
        audience=_audience(db, e),
        group_id=e.group_id,
        expense_id=e.id,
        data={"changes": changes},
    )
    db.flush()
    db.expire(e)  # reload relationships (e.g. a new payer) inside the same transaction
    out = expense_out(_load_visible(db, e.id, user), user.id)
    finish(db, dry_run)
    return out


@router.delete("/{expense_id}", response_model=ExpenseOut)
def delete_expense(
    expense_id: int,
    dry_run: bool = DryRun,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExpenseOut:
    """Soft delete: the row stays (for the activity log / undo) but stops counting toward balances."""
    e = _load_visible(db, expense_id, user)
    e.deleted_at = dt.datetime.now(dt.UTC)
    log_activity(
        db,
        actor=user,
        verb="expense_deleted",
        summary=f'{user.name} deleted "{e.description}" ({money(e.amount, e.currency)})',
        audience=_audience(db, e),
        group_id=e.group_id,
        expense_id=e.id,
    )
    out = expense_out(e, user.id)
    finish(db, dry_run)
    return out
