from fastapi import APIRouter, Depends

from app.dependencies.auth import get_current_user, require_role
from app.models.user import User
from app.schemas.user import UserOut

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
async def read_current_user(current_user: User = Depends(get_current_user)):
    return current_user


@router.get("/admin-only", response_model=UserOut)
async def admin_only_example(current_user: User = Depends(require_role("admin"))):
    """Example of a role-gated route — pattern to reuse for RAG admin endpoints (e.g. reindexing, source management)."""
    return current_user
