import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import Group, GroupMember, User
from .security import decode_access_token

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Every protected endpoint resolves the caller from THEIR token.

    This is why the MCP server forwards the end user's JWT: the API's authorization
    rules (e.g. "only members can read a group") are enforced per real user.
    """
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Missing or invalid token. Log in again to get a fresh one.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if creds is None:
        raise unauthorized
    try:
        user_id = decode_access_token(creds.credentials)
    except jwt.PyJWTError:
        raise unauthorized from None
    user = db.get(User, user_id)
    if user is None:
        raise unauthorized
    return user


def require_group_member(db: Session, group_id: int, user: User) -> Group:
    """Load a group the user belongs to. Non-members get 404 (not 403) so ids can't be probed."""
    group = db.get(Group, group_id)
    is_member = db.scalar(
        select(GroupMember.id).where(
            GroupMember.group_id == group_id, GroupMember.user_id == user.id
        )
    )
    if group is None or not is_member:
        raise HTTPException(404, f"Group {group_id} not found, or you are not a member of it.")
    return group
