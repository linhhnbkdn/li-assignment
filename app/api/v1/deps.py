import logging

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.auth import AuthError, decode_token, decode_token_unverified
from app.core.db import get_db
from app.core.rate_limiter import RateLimitExceeded
from app.models.user import User
from app.repos.org_repo import OrgRepository

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        unverified = decode_token_unverified(token=token)
        org_id = unverified.get("org_id")
        if not org_id:
            raise credentials_exc

        org_repo = OrgRepository(db=db)
        org = org_repo.get_by_id(org_id=org_id)
        if org is None:
            raise credentials_exc

        payload = decode_token(token=token, secret=org.secret)
        user_id = payload.get("sub")
        if not user_id:
            raise credentials_exc

        user = db.get(User, user_id)
        if user is None or user.org_id != org_id:
            raise credentials_exc

        return user
    except AuthError:
        raise credentials_exc


def require_rate_limit(
    request: Request,
    user: User = Depends(get_current_user),
) -> None:
    limiter = request.app.state.rate_limiter
    try:
        limiter.check(user_id=user.id)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Retry after {exc.retry_after}s.",
            headers={"Retry-After": str(exc.retry_after)},
        )
