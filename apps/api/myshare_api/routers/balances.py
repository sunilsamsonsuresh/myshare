from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, require_group_member
from ..models import User
from ..schemas import BalancesOut, OverallBalanceOut
from ..services.balances import overall_for, user_ledger
from ..services.common import friend_ids, get_user_or_404, group_detail_out
from .users import friend_detail_out

router = APIRouter(prefix="/balances", tags=["balances"])


@router.get("", response_model=BalancesOut)
def get_balances(
    scope: Literal["overall", "friend", "group"] = "overall",
    id: int | None = Query(None, description="friend id (scope=friend) or group id (scope=group)"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BalancesOut:
    if scope == "overall":
        return BalancesOut(
            scope=scope,
            overall=[
                OverallBalanceOut(**vars(b)) for b in overall_for(user_ledger(db, user.id), user.id)
            ],
        )
    if id is None:
        raise HTTPException(422, f"scope={scope} needs an id (the {scope}'s id).")
    if scope == "friend":
        if id not in friend_ids(db, user.id):
            raise HTTPException(404, f"User {id} is not one of your friends.")
        return BalancesOut(scope=scope, friend=friend_detail_out(db, user, get_user_or_404(db, id)))
    return BalancesOut(
        scope=scope, group=group_detail_out(db, require_group_member(db, id, user), user.id)
    )
