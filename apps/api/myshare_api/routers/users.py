from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..deps import get_current_user
from ..models import Expense, ExpenseSplit, Group, GroupMember, Settlement, User
from ..schemas import (
    FriendAddIn,
    FriendDetailOut,
    FriendGroupBalance,
    FriendOut,
    Money,
    OverallBalanceOut,
    PersonMatch,
    ResolveOut,
    SummaryOut,
    UserOut,
)
from ..services.balances import build_ledger, overall_for, user_ledger
from ..services.common import DryRun, finish, friend_ids, log_activity, make_friends, user_out

router = APIRouter(tags=["users"])


@router.get("/users/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return user_out(user)


@router.get("/users/me/summary", response_model=SummaryOut)
def my_summary(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> SummaryOut:
    ledger = user_ledger(db, user.id)
    groups = (
        db.scalar(
            select(func.count()).select_from(GroupMember).where(GroupMember.user_id == user.id)
        )
        or 0
    )
    return SummaryOut(
        user=user_out(user),
        default_currency=user.default_currency,
        balances=[OverallBalanceOut(**vars(b)) for b in overall_for(ledger, user.id)],
        friend_count=len(friend_ids(db, user.id)),
        group_count=groups,
    )


def _friend_balances(ledger, me: int, other: int) -> list[Money]:
    return [Money(currency=c, amount=a) for c, a in sorted(ledger.between(me, other).items())]


@router.get("/friends", response_model=list[FriendOut])
def list_friends(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[FriendOut]:
    ledger = user_ledger(db, user.id)
    ids = friend_ids(db, user.id)
    friends = db.scalars(select(User).where(User.id.in_(ids)).order_by(User.name)).all()
    return [
        FriendOut(**user_out(f).model_dump(), balances=_friend_balances(ledger, user.id, f.id))
        for f in friends
    ]


@router.post("/friends", response_model=FriendOut, status_code=201)
def add_friend(
    body: FriendAddIn,
    dry_run: bool = DryRun,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FriendOut:
    other = db.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    if other is None:
        raise HTTPException(
            404,
            f"No MyShare user has the email {body.email}. They need to sign up first "
            "(invitations aren't supported yet).",
        )
    if other.id == user.id:
        raise HTTPException(400, "You can't add yourself as a friend.")
    if make_friends(db, user.id, other.id):
        log_activity(
            db,
            actor=user,
            verb="friend_added",
            summary=f"{user.name} added {other.name} as a friend",
            audience=[other.id],
        )
    ledger = user_ledger(db, user.id)
    out = FriendOut(
        **user_out(other).model_dump(), balances=_friend_balances(ledger, user.id, other.id)
    )
    finish(db, dry_run)
    return out


@router.get("/friends/{friend_id}", response_model=FriendDetailOut)
def friend_detail(
    friend_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> FriendDetailOut:
    if friend_id not in friend_ids(db, user.id):
        raise HTTPException(404, f"User {friend_id} is not one of your friends.")
    friend = db.get(User, friend_id)
    assert friend is not None
    return friend_detail_out(db, user, friend)


def friend_detail_out(db: Session, user: User, friend: User) -> FriendDetailOut:
    """Balance with a friend overall plus a per-group breakdown."""
    full = user_ledger(db, user.id)
    pair = [user.id, friend.id]
    candidates = db.scalars(
        select(Expense)
        .where(
            Expense.deleted_at.is_(None),
            or_(
                Expense.payer_id.in_(pair),
                Expense.id.in_(
                    select(ExpenseSplit.expense_id).where(ExpenseSplit.user_id.in_(pair))
                ),
            ),
        )
        .options(selectinload(Expense.splits))
    )
    # Keep only expenses where both of them are involved (as payer or participant).
    expenses = [
        e for e in candidates if set(pair) <= ({e.payer_id} | {s.user_id for s in e.splits})
    ]
    settlements = db.scalars(
        select(Settlement).where(
            Settlement.deleted_at.is_(None),
            or_(
                (Settlement.from_user_id == user.id) & (Settlement.to_user_id == friend.id),
                (Settlement.from_user_id == friend.id) & (Settlement.to_user_id == user.id),
            ),
        )
    ).all()
    by_group: dict[int | None, tuple[list, list]] = defaultdict(lambda: ([], []))
    for e in expenses:
        by_group[e.group_id][0].append(e)
    for s in settlements:
        by_group[s.group_id][1].append(s)
    names = {
        g.id: g.name
        for g in db.scalars(select(Group).where(Group.id.in_([k for k in by_group if k])))
    }
    breakdown = []
    for gid, (exps, sets) in by_group.items():
        bal = _friend_balances(build_ledger(exps, sets), user.id, friend.id)
        if bal:
            breakdown.append(
                FriendGroupBalance(
                    group_id=gid,
                    group_name=names[gid] if gid else "Non-group expenses",
                    balances=bal,
                )
            )
    return FriendDetailOut(
        **user_out(friend).model_dump(),
        balances=_friend_balances(full, user.id, friend.id),
        breakdown=breakdown,
    )


@router.get("/people/resolve", response_model=ResolveOut)
def resolve_person(
    name: str = Query(min_length=1, description="A name, partial name, or email"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ResolveOut:
    """Find people the caller knows (themselves, friends, co-members of their groups) by name or email.

    Only people the caller already has a relationship with are searchable: this
    prevents the endpoint from being used to enumerate every user in the system.
    """
    q = name.strip().lower()
    known: dict[int, str] = {}
    if q in {"me", "i", "myself", "you"}:
        return ResolveOut(
            query=name, matches=[PersonMatch(**user_out(user).model_dump(), via="you")]
        )
    for fid in friend_ids(db, user.id):
        known[fid] = "friend"
    my_groups = select(GroupMember.group_id).where(GroupMember.user_id == user.id)
    for gm in db.scalars(
        select(GroupMember)
        .where(GroupMember.group_id.in_(my_groups))
        .options(selectinload(GroupMember.group))
    ):
        known.setdefault(gm.user_id, f"group: {gm.group.name}")
    known[user.id] = "you"
    people = db.scalars(select(User).where(User.id.in_(known))).all()

    def score(u: User) -> int | None:
        n, e = u.name.lower(), u.email.lower()
        if q in (n, e):
            return 0
        if any(part == q for part in n.split()):
            return 1
        if n.startswith(q) or e.startswith(q):
            return 2
        if q in n or q in e:
            return 3
        return None

    scored = sorted(
        ((s, u) for u in people if (s := score(u)) is not None), key=lambda t: (t[0], t[1].name)
    )
    if scored and scored[0][0] <= 1:  # keep only the best tier when there are strong matches
        best = scored[0][0]
        scored = [t for t in scored if t[0] == best]
    return ResolveOut(
        query=name,
        matches=[PersonMatch(**user_out(u).model_dump(), via=known[u.id]) for _, u in scored],
    )
