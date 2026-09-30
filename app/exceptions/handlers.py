"""
Centralized translation of domain exceptions -> HTTP responses.

This is the ONE place that maps AppError subtypes to status codes. Adding
a new domain exception means adding one line here — no endpoint needs a
try/except for it. Register with `register_exception_handlers(app)` in
main.py.
"""
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.exceptions.base import (
    AppError,
    FileTooLargeError,
    GuardrailViolationError,
    IngestionError,
    InsufficientPermissionsError,
    InvalidCredentialsError,
    InvalidTokenError,
    ModelNotFoundError,
    RetrievalError,
    TokenExpiredError,
    UserAlreadyExistsError,
    UserNotFoundError,
)
from app.logging import get_logger

logger = get_logger(__name__)

_STATUS_MAP: dict[type[AppError], int] = {
    InvalidCredentialsError: status.HTTP_401_UNAUTHORIZED,
    InvalidTokenError: status.HTTP_401_UNAUTHORIZED,
    TokenExpiredError: status.HTTP_401_UNAUTHORIZED,
    UserAlreadyExistsError: status.HTTP_409_CONFLICT,
    UserNotFoundError: status.HTTP_404_NOT_FOUND,
    InsufficientPermissionsError: status.HTTP_403_FORBIDDEN,
    GuardrailViolationError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    RetrievalError: status.HTTP_502_BAD_GATEWAY,
    IngestionError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    FileTooLargeError: status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
    ModelNotFoundError: status.HTTP_503_SERVICE_UNAVAILABLE,
}


def register_exception_handlers(app: FastAPI, *, is_production: bool) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        status_code = _STATUS_MAP.get(type(exc), status.HTTP_400_BAD_REQUEST)
        # 401s use WWW-Authenticate per spec; keep the header for auth errors.
        headers = {"WWW-Authenticate": "Bearer"} if status_code == status.HTTP_401_UNAUTHORIZED else None
        return JSONResponse(status_code=status_code, content={"detail": exc.message}, headers=headers)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.error("unhandled_exception", error=str(exc), path=request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"} if is_production else {"detail": str(exc)},
        )
