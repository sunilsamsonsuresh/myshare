from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, require_group_member
from ..models import Activity, Expense, Group, GroupMember, Settlement, User
from ..schemas import (
    GroupCreateIn,
    GroupDetailOut,
    GroupOut,
    GroupUpdateIn,
    MemberAddIn,
    SimplifiedDebtsOut,
    TransferOut,
)
from ..services.balances import group_ledger
from ..services.common import (
    DryRun,
    finish,
    group_detail_out,
    group_out,
    log_activity,
    make_friends,
    member_ids,
    money,
    user_out,
)
from ..services.simplify import simplify_debts

router = APIRouter(prefix="/groups", tags=["groups"])


def _find_user_by_email(db: Session, email: str) -> User:
    u = db.scalar(select(User).where(func.lower(User.email) == email.lower()))
    if u is None:
        raise HTTPException(
            404, f"No MyShare user has the email {email}. They need to sign up first."
        )
    return u


def _add_member(db: Session, group: Group, new: User) -> None:
    existing = member_ids(db, group.id)
    db.add(GroupMember(group_id=group.id, user_id=new.id))
    # Like Splitwise: everyone in a group becomes friends, so 1:1 balances work.
    for uid in existing:
        make_friends(db, uid, new.id)


@router.get("", response_model=list[GroupOut])
def list_groups(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[GroupOut]:
    groups = db.scalars(
        select(Group)
        .join(GroupMember, GroupMember.group_id == Group.id)
        .where(GroupMember.user_id == user.id)
        .order_by(Group.created_at.desc())
    ).all()
    return [group_out(db, g, user.id) for g in groups]


@router.post("", response_model=GroupDetailOut, status_code=201)
def create_group(
    body: GroupCreateIn,
    dry_run: bool = DryRun,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GroupDetailOut:
    # Resolve every email first so a typo fails the whole request instead of half-creating a group.
    members = [
        _find_user_by_email(db, e) for e in dict.fromkeys(x.lower() for x in body.member_emails)
    ]
    group = Group(
        name=body.name.strip(), kind=body.kind, currency=body.currency, created_by=user.id
    )
    db.add(group)
    db.flush()
    _add_member(db, group, user)
    for m in members:
        if m.id != user.id:
            _add_member(db, group, m)
    db.flush()
    log_activity(
        db,
        actor=user,
        verb="group_created",
        summary=f'{user.name} created the group "{group.name}"',
        audience=member_ids(db, group.id),
        group_id=group.id,
    )
    db.refresh(group)
    out = group_detail_out(db, group, user.id)
    finish(db, dry_run)
    return out


@router.get("/{group_id}", response_model=GroupDetailOut)
def get_group(
    group_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> GroupDetailOut:
    return group_detail_out(db, require_group_member(db, group_id, user), user.id)


@router.patch("/{group_id}", response_model=GroupDetailOut)
def update_group(
    group_id: int,
    body: GroupUpdateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GroupDetailOut:
    group = require_group_member(db, group_id, user)
    if body.name is not None:
        group.name = body.name.strip()
    if body.kind is not None:
        group.kind = body.kind
    db.commit()
    return group_detail_out(db, group, user.id)


@router.delete("/{group_id}", response_model=GroupDetailOut)
def delete_group(
    group_id: int,
    dry_run: bool = DryRun,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GroupDetailOut:
    """Permanently delete a group with all its expenses and settlements.

    Any member may do it, but only once everyone is settled up: deleting a group
    with open balances would silently erase money people still owe each other.
    """
    group = require_group_member(db, group_id, user)
    nets = group_ledger(db, group_id).nets().get(group.currency, {})
    unsettled = {uid: n for uid, n in nets.items() if n}
    if unsettled:
        names = {u.id: u.name for u in db.scalars(select(User).where(User.id.in_(unsettled)))}
        owing = ", ".join(
            f"{names[uid]} {'gets back' if n > 0 else 'owes'} {money(abs(n), group.currency)}"
            for uid, n in sorted(unsettled.items(), key=lambda kv: kv[1])
        )
        raise HTTPException(
            409,
            f'"{group.name}" can\'t be deleted until everyone is settled up ({owing}). '
            "Record the payments under Settle up first.",
        )

    out = group_detail_out(db, group, user.id)
    audience = member_ids(db, group_id)
    expense_ids = select(Expense.id).where(Expense.group_id == group_id)
    settlement_ids = select(Settlement.id).where(Settlement.group_id == group_id)
    # Keep the activity history (it still reads fine: 'Sunil added "Dinner" in Goa Trip'),
    # but detach it from the rows that are about to disappear.
    db.execute(
        update(Activity)
        .where(
            or_(
                Activity.group_id == group_id,
                Activity.expense_id.in_(expense_ids),
                Activity.settlement_id.in_(settlement_ids),
            )
        )
        .values(group_id=None, expense_id=None, settlement_id=None)
    )
    for e in db.scalars(select(Expense).where(Expense.group_id == group_id)):
        db.delete(e)  # its splits go with it (cascade)
    for st in db.scalars(select(Settlement).where(Settlement.group_id == group_id)):
        db.delete(st)
    db.delete(group)  # its memberships go with it (cascade)
    db.flush()
    log_activity(
        db,
        actor=user,
        verb="group_deleted",
        summary=f'{user.name} deleted the group "{group.name}"',
        audience=audience,
    )
    finish(db, dry_run)
    return out


@router.post("/{group_id}/members", response_model=GroupDetailOut, status_code=201)
def add_member(
    group_id: int,
    body: MemberAddIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GroupDetailOut:
    group = require_group_member(db, group_id, user)
    new = _find_user_by_email(db, body.email)
    if new.id in member_ids(db, group.id):
        raise HTTPException(409, f"{new.name} is already a member of {group.name}.")
    _add_member(db, group, new)
    db.flush()
    log_activity(
        db,
        actor=user,
        verb="member_added",
        summary=f'{user.name} added {new.name} to "{group.name}"',
        audience=member_ids(db, group.id),
        group_id=group.id,
    )
    db.commit()
    db.refresh(group)
    return group_detail_out(db, group, user.id)


@router.delete("/{group_id}/members/{user_id}", response_model=GroupDetailOut)
def remove_member(
    group_id: int,
    user_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GroupDetailOut:
    group = require_group_member(db, group_id, user)
    gm = db.scalar(
        select(GroupMember).where(GroupMember.group_id == group_id, GroupMember.user_id == user_id)
    )
    if gm is None:
        raise HTTPException(404, f"User {user_id} is not a member of {group.name}.")
    balance = group_ledger(db, group_id).nets().get(group.currency, {}).get(user_id, 0)
    if balance:
        raise HTTPException(
            409,
            f'{gm.user.name} can\'t leave "{group.name}" with a non-zero balance '
            f"({money(balance, group.currency)}). Settle up first.",
        )
    audience = member_ids(db, group_id)
    name = gm.user.name
    db.delete(gm)
    log_activity(
        db,
        actor=user,
        verb="member_removed",
        summary=f'{user.name} removed {name} from "{group.name}"',
        audience=audience,
        group_id=group.id,
    )
    db.commit()
    db.refresh(group)
    return group_detail_out(db, group, user.id)


@router.get("/{group_id}/simplified-debts", response_model=SimplifiedDebtsOut)
def simplified_debts(
    group_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> SimplifiedDebtsOut:
    group = require_group_member(db, group_id, user)
    ledger = group_ledger(db, group_id)
    nets = ledger.nets().get(group.currency, {})
    # Count pairwise debts after netting each pair, to show how much simplifying saved.
    pairs = {tuple(sorted((d, c))) for (d, c, cur) in ledger.debts if cur == group.currency}
    original = sum(1 for a, b in pairs if ledger.between(a, b).get(group.currency))
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(nets)))}
    return SimplifiedDebtsOut(
        group_id=group.id,
        group_name=group.name,
        currency=group.currency,
        transfers=[
            TransferOut(
                from_user=user_out(users[t.from_user_id]),
                to_user=user_out(users[t.to_user_id]),
                amount=t.amount,
            )
            for t in simplify_debts(nets)
        ],
        original_transfer_count=original,
    )
