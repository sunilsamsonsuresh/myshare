from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..deps import get_current_user, require_group_member
from ..models import Activity, ActivityAudience, User
from ..schemas import ActivityOut
from ..services.common import user_out

router = APIRouter(prefix="/activity", tags=["activity"])


@router.get("", response_model=list[ActivityOut])
def list_activity(
    group_id: int | None = None,
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ActivityOut]:
    stmt = select(Activity).options(selectinload(Activity.actor))
    if group_id is not None:
        require_group_member(db, group_id, user)
        stmt = stmt.where(Activity.group_id == group_id)
    else:
        stmt = stmt.where(
            Activity.id.in_(
                select(ActivityAudience.activity_id).where(ActivityAudience.user_id == user.id)
            )
        )
    stmt = stmt.order_by(Activity.created_at.desc(), Activity.id.desc()).limit(limit)
    return [
        ActivityOut(
            id=a.id,
            verb=a.verb,
            summary=a.summary,
            actor=user_out(a.actor),
            group_id=a.group_id,
            expense_id=a.expense_id,
            settlement_id=a.settlement_id,
            data=a.data,
            created_at=a.created_at,
        )
        for a in db.scalars(stmt)
    ]
