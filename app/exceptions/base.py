"""
Domain-level exceptions, decoupled from HTTP and from FastAPI entirely.

Services raise these. `app/exceptions/handlers.py` registers FastAPI
exception handlers that translate them into HTTP responses in ONE place —
individual endpoints do not need try/except blocks for domain errors. This
keeps `services/` importable from anywhere (CLI scripts, workers, tests)
without a FastAPI dependency.
"""


class AppError(Exception):
    """Base class for all domain errors. Never raise this directly —
    raise a specific subtype so it maps to the right HTTP status."""
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


# --- Auth / identity ---

class InvalidCredentialsError(AppError):
    pass


class UserAlreadyExistsError(AppError):
    pass


class UserNotFoundError(AppError):
    pass


class InvalidTokenError(AppError):
    pass


class TokenExpiredError(AppError):
    pass


class InsufficientPermissionsError(AppError):
    pass


# --- Reserved for RAG-specific error paths ---

class GuardrailViolationError(AppError):
    """Raised when a guardrail blocks input/output content."""
    pass


class RetrievalError(AppError):
    """Raised on RAG retrieval failures (vector store errors, empty index, etc.)."""
    pass


class IngestionError(AppError):
    """Raised when a document fails to parse, chunk, or embed during ingestion."""
    pass


class ModelNotFoundError(AppError):
    """A required ML model isn't downloaded on the server. The message is
    returned to the client, so it names the model and the fix but never a
    filesystem path (those go to the server log only)."""
    pass


class FileTooLargeError(AppError):
    """Uploaded file exceeds RAG_MAX_UPLOAD_MB."""
    pass
