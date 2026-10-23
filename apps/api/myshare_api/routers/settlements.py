import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..deps import get_current_user, require_group_member
from ..models import Settlement, User
from ..schemas import SettlementCreateIn, SettlementOut
from ..services.common import (
    DryRun,
    finish,
    friend_ids,
    get_user_or_404,
    log_activity,
    member_ids,
    money,
    settlement_out,
)

router = APIRouter(prefix="/settlements", tags=["settlements"])


@router.post("", response_model=SettlementOut, status_code=201)
def create_settlement(
    body: SettlementCreateIn,
    dry_run: bool = DryRun,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SettlementOut:
    if body.from_user_id == body.to_user_id:
        raise HTTPException(422, "A payment needs two different people.")
    payer = get_user_or_404(db, body.from_user_id, "Payer")
    payee = get_user_or_404(db, body.to_user_id, "Recipient")

    if body.group_id is not None:
        group = require_group_member(db, body.group_id, user)
        members = member_ids(db, group.id)
        if payer.id not in members or payee.id not in members:
            raise HTTPException(
                422, f'Both {payer.name} and {payee.name} must be members of "{group.name}".'
            )
        currency = body.currency or group.currency
        if currency != group.currency:
            raise HTTPException(
                422,
                f'"{group.name}" uses {group.currency}; record the payment in {group.currency}.',
            )
        audience = members
    else:
        # A non-group payment must involve the caller, and the other person must be their friend.
        if user.id not in (payer.id, payee.id):
            raise HTTPException(
                403, "You can only record non-group payments that you made or received."
            )
        other = payee.id if payer.id == user.id else payer.id
        if other not in friend_ids(db, user.id):
            raise HTTPException(404, f"User {other} is not one of your friends.")
        currency = body.currency or user.default_currency
        audience = [payer.id, payee.id]

    s = Settlement(
        group_id=body.group_id,
        from_user_id=payer.id,
        to_user_id=payee.id,
        amount=body.amount,
        currency=currency,
        date=body.date or dt.date.today(),
        note=body.note,
        created_by=user.id,
    )
    db.add(s)
    db.flush()
    log_activity(
        db,
        actor=user,
        verb="settlement_added",
        summary=f"{payer.name} paid {payee.name} {money(s.amount, currency)}",
        audience=audience,
        group_id=s.group_id,
        settlement_id=s.id,
        data={"amount": s.amount, "currency": currency},
    )
    db.refresh(s)
    out = settlement_out(s)
    finish(db, dry_run)
    return out


@router.get("", response_model=list[SettlementOut])
def list_settlements(
    group_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SettlementOut]:
    stmt = (
        select(Settlement)
        .where(Settlement.deleted_at.is_(None))
        .options(selectinload(Settlement.from_user), selectinload(Settlement.to_user))
        .order_by(Settlement.date.desc(), Settlement.id.desc())
    )
    if group_id is not None:
        require_group_member(db, group_id, user)
        stmt = stmt.where(Settlement.group_id == group_id)
    else:
        stmt = stmt.where(or_(Settlement.from_user_id == user.id, Settlement.to_user_id == user.id))
    return [settlement_out(s) for s in db.scalars(stmt)]
