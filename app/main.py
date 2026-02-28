"""
FastAPI application factory — the main entry point.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.health import router as health_router
from app.api.v1.router import router as v1_router
from app.config import get_settings
from app.database import engine, Base
from app.middleware.idempotency import idempotency_service
from app.middleware.rate_limiter import rate_limiter
from app.utils.exceptions import register_exception_handlers, AuthenticationError, RateLimitError
from app.utils.logging import setup_logging, generate_correlation_id, correlation_id_ctx

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    setup_logging()
    settings = get_settings()
    logger.info(
        f"Starting {settings.app_name} v{settings.app_version} "
        f"[env={settings.environment}]"
    )

    # Create tables (in production, use Alembic migrations instead)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created/verified")

    yield

    # Shutdown
    logger.info("Shutting down...")
    await idempotency_service.close()
    await rate_limiter.close()
    await engine.dispose()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Production-ready payment microservice with Stripe integration. "
            "Provides a complete payment processing API including payments, "
            "refunds, customer management, receipt generation, and webhook handling.\n\n"
            "## Authentication\n"
            "All API endpoints (except health checks and webhooks) require an "
            "`X-API-Key` header for authentication.\n\n"
            "## Idempotency\n"
            "POST endpoints support the `Idempotency-Key` header to prevent "
            "duplicate operations.\n\n"
            "## Rate Limiting\n"
            "API requests are rate-limited per API key. Check the "
            "`X-RateLimit-*` response headers for current limits."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
        openapi_tags=[
            {
                "name": "Payments",
                "description": "Create, retrieve, confirm, and cancel payments.",
            },
            {
                "name": "Refunds",
                "description": "Create and manage refunds for existing payments.",
            },
            {
                "name": "Customers",
                "description": "Manage customers synced with Stripe.",
            },
            {
                "name": "Receipts",
                "description": "Generate and download PDF receipts.",
            },
            {
                "name": "Webhooks",
                "description": "Receive and process Stripe webhook events.",
            },
            {
                "name": "Health",
                "description": "Service health and readiness probes.",
            },
        ],
    )

    # ── CORS ─────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # In production, restrict to specific origins
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset",
        ],
    )

    # ── Exception Handlers ───────────────────────────
    register_exception_handlers(app)

    # ── Middleware: Correlation ID + Auth + Rate Limiting ─
    @app.middleware("http")
    async def middleware_stack(request: Request, call_next):
        # 1. Correlation ID
        corr_id = request.headers.get("X-Correlation-ID", generate_correlation_id())
        correlation_id_ctx.set(corr_id)

        # 2. Skip auth and rate limiting for health, docs, webhooks, and openapi
        path = request.url.path
        skip_paths = ("/health", "/ready", "/docs", "/redoc", "/openapi.json", "/api/v1/webhooks")
        skip_auth = any(path.startswith(p) for p in skip_paths)

        if not skip_auth:
            # Authentication
            api_key = request.headers.get("X-API-Key")
            if not api_key or api_key != settings.api_key:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={
                        "error": {
                            "type": "authentication_error",
                            "title": "AuthenticationError",
                            "status": 401,
                            "detail": "Invalid or missing API key",
                            "instance": str(request.url),
                        }
                    },
                )

            # Rate limiting
            allowed, rate_headers = await rate_limiter.is_allowed(api_key)
            if not allowed:
                response = JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "error": {
                            "type": "rate_limit_error",
                            "title": "RateLimitError",
                            "status": 429,
                            "detail": "Rate limit exceeded. Please try again later.",
                            "instance": str(request.url),
                        }
                    },
                )
                for key, val in rate_headers.items():
                    response.headers[key] = val
                return response

        # 3. Process request
        response = await call_next(request)

        # 4. Add correlation ID to response
        response.headers["X-Correlation-ID"] = corr_id

        # 5. Add rate limit headers if authenticated
        if not skip_auth:
            for key, val in rate_headers.items():
                response.headers[key] = val

        return response

    # ── Routers ──────────────────────────────────────
    app.include_router(health_router)
    app.include_router(v1_router)

    return app


# Application instance
app = create_app()
