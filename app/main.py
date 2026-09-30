import warnings

# Suppress Pydantic protected namespace UserWarnings from third-party libraries
warnings.filterwarnings(
    "ignore",
    category=UserWarning,
    message=".*conflict with protected namespace.*",
)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.exceptions import register_exception_handlers
from app.logging import add_request_id, configure_logging, get_logger

settings = get_settings()
configure_logging(debug=settings.DEBUG)
logger = get_logger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        debug=settings.DEBUG,
        docs_url="/docs" if not settings.is_production else None,  # hide Swagger in prod
        redoc_url=None,
    )

    # --- CORS ---
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Rate limiting (protects /auth/login from brute force) ---
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    # --- Request correlation ID, for tracing multi-step RAG/agent requests ---
    app.middleware("http")(add_request_id)

    # --- Domain exceptions -> HTTP responses, in one place (app/exceptions) ---
    register_exception_handlers(app, is_production=settings.is_production)

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    @app.get("/health")
    async def health_check():
        return {"status": "ok", "environment": settings.ENVIRONMENT}

    return app


app = create_app()
