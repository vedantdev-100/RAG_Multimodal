"""
FastAPI dependency-injection layer for auth. This is the ONLY place that
should translate domain exceptions into HTTPException — keeps services/
framework-agnostic.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.session import get_db_session
from app.models.user import User
from app.repositories.user_repository import UserRepository

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_db_session),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        if payload.get("type") != "access":
            raise credentials_exception
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    repo = UserRepository(session)
    user = await repo.get_by_id(user_id)
    if user is None or not user.is_active:
        raise credentials_exception
    return user


def require_scopes(*required_scopes: str):
    """
    Usage: @router.get(..., dependencies=[Depends(require_scopes("rag:ingest"))])
    Scoped authorization, designed so future RAG endpoints can gate
    access at the route level without touching business logic.
    """
    async def _checker(current_user: User = Depends(get_current_user)) -> User:
        user_scopes = set(current_user.scope_list())
        if current_user.role == "admin":
            return current_user  # admins bypass fine-grained scope checks
        if not set(required_scopes).issubset(user_scopes):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required scope(s): {', '.join(required_scopes)}",
            )
        return current_user

    return _checker


def require_role(*allowed_roles: str):
    async def _checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )
        return current_user

    return _checker
