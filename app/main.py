"""
FastAPI application factory — the main entry point.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.models import APIKey, APIKeyIn, SecuritySchemeType
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.health import router as health_router
from app.api.v1.router import router as v1_router
from app.config import get_settings
from app.database import engine, Base, get_db
from app.middleware.idempotency import idempotency_service
from app.middleware.rate_limiter import rate_limiter
from app.services.api_key_service import api_key_service
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

    # In production, use Alembic migrations instead of creating tables here.
    logger.info("Database connection established")

    yield

    # Shutdown
    logger.info("Shutting down...")
    await idempotency_service.close()
    await rate_limiter.close()
    await api_key_service.close()
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
            "`X-API-Key` header for authentication. Click the **Authorize** button "
            "(🔒) above to enter your API key, and it will be included in all requests.\n\n"
            "- **Admin key**: Set via `ADMIN_API_KEY` env var — used to manage tenant API keys\n"
            "- **Tenant keys**: Created via `POST /api/v1/admin/api-keys` — used for payment operations\n\n"
            "## Idempotency\n"
            "POST endpoints support the `Idempotency-Key` header to prevent "
            "duplicate operations.\n\n"
            "## Rate Limiting\n"
            "API requests are rate-limited per API key. Each tenant key can have "
            "custom rate limits. Check the `X-RateLimit-*` response headers for current limits."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
        swagger_ui_parameters={"persistAuthorization": True},
        openapi_tags=[
            {
                "name": "Checkout",
                "description": (
                    "**Start here.** Create a hosted checkout session and redirect "
                    "the end-user to Stripe's payment page. This is the main "
                    "integration point for client services."
                ),
            },
            {
                "name": "Payments",
                "description": "Create, retrieve, confirm, cancel/refund payments, and download receipts.",
            },
            {
                "name": "Customers",
                "description": "Manage customers synced with Stripe.",
            },
            {
                "name": "Webhooks",
                "description": "Receive and process Stripe webhook events.",
            },
            {
                "name": "API Keys",
                "description": "Manage tenant API keys (admin only).",
            },
            {
                "name": "Health",
                "description": "Service health and readiness probes.",
            },
        ],
    )

    # ── OpenAPI Security Scheme ──────────────────────
    # This makes the 🔒 Authorize button appear in Swagger UI
    # and adds X-API-Key to all generated curl commands
    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        from fastapi.openapi.utils import get_openapi
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
            tags=app.openapi_tags,
        )
        # Add API key security scheme
        schema["components"] = schema.get("components", {})
        schema["components"]["securitySchemes"] = {
            "ApiKeyAuth": {
                "type": "apiKey",
                "in": "header",
                "name": "X-API-Key",
                "description": (
                    "Enter your API key. Use the **admin key** (from ADMIN_API_KEY env var) "
                    "for `/api/v1/admin/*` endpoints, or a **tenant key** (ps_live_...) "
                    "for payment/refund/customer operations."
                ),
            }
        }
        # Apply globally to all endpoints
        schema["security"] = [{"ApiKeyAuth": []}]
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi

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

        # 2. Skip auth and rate limiting for health, docs, webhooks, openapi, and the public checkout page
        path = request.url.path
        skip_paths = (
            "/health", "/ready", "/docs", "/redoc", "/openapi.json", 
            "/api/v1/webhooks", "/checkout/", "/static", "/app/", "/api/v1/auth/"
        )
        skip_auth = any(path.startswith(p) for p in skip_paths)
        
        # Make GET /sessions/{id} and POST /sessions/{id}/authorize public
        if path.startswith("/api/v1/checkout/sessions/"):
            # Only allow if there's a specific ID after /sessions/
            parts = path.split("/")
            if len(parts) >= 6 and parts[5]:  # /api/v1/checkout/sessions/{id}
                if request.method == "GET" or parts[-1] == "authorize":
                    skip_auth = True
                skip_auth = True

        rate_headers = {}

        if not skip_auth:
            # Extract API key from header
            raw_key = request.headers.get("X-API-Key")
            if not raw_key:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={
                        "error": {
                            "type": "authentication_error",
                            "title": "AuthenticationError",
                            "status": 401,
                            "detail": "Missing API key. Include an X-API-Key header.",
                            "instance": str(request.url),
                        }
                    },
                )

            # Check if it's the admin key
            is_admin = (raw_key == settings.admin_api_key)

            # Admin-only endpoints
            is_admin_endpoint = path.startswith("/api/v1/admin/")
            if is_admin_endpoint and not is_admin:
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={
                        "error": {
                            "type": "authorization_error",
                            "title": "ForbiddenError",
                            "status": 403,
                            "detail": "Admin API key required for this endpoint.",
                            "instance": str(request.url),
                        }
                    },
                )

            if not is_admin:
                # Validate tenant key against database
                from app.database import async_session
                async with async_session() as db:
                    api_key_record = await api_key_service.validate_key(db, raw_key)
                    await db.commit()

                if not api_key_record:
                    return JSONResponse(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        content={
                            "error": {
                                "type": "authentication_error",
                                "title": "AuthenticationError",
                                "status": 401,
                                "detail": "Invalid, revoked, or expired API key.",
                                "instance": str(request.url),
                            }
                        },
                    )

                # Store the API key record on request.state for downstream use
                request.state.api_key = api_key_record
                request.state.client_name = api_key_record.client_name

                # Use per-key rate limits if configured, otherwise global defaults
                rl_requests = api_key_record.rate_limit_requests or settings.rate_limit_requests
                rl_window = api_key_record.rate_limit_window_seconds or settings.rate_limit_window_seconds
            else:
                # Admin key identified
                request.state.api_key = None
                request.state.client_name = "__admin__"
                rl_requests = settings.rate_limit_requests
                rl_window = settings.rate_limit_window_seconds

            # Rate limiting (per raw key)
            allowed, rate_headers = await rate_limiter.is_allowed(raw_key)
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

    # ── Static Files & Frontend ──────────────────────
    import os
    os.makedirs("app/static", exist_ok=True)
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    @app.get("/app/register", summary="Digital Wallet Registration UI")
    async def get_register_ui(request: Request):
        from fastapi.templating import Jinja2Templates
        import os
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "static"))
        return templates.TemplateResponse("register.html", {"request": request})

    @app.get("/app/dashboard", summary="Digital Wallet Dashboard UI")
    async def get_dashboard_ui(request: Request):
        from fastapi.templating import Jinja2Templates
        import os
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "static"))
        return templates.TemplateResponse("dashboard.html", {"request": request})

    @app.get("/checkout/{session_id}", summary="Hosted Checkout UI", response_class=FileResponse, tags=["Checkout UI"])
    async def render_checkout(session_id: str):
        """Serve the hosted checkout HTML page."""
        return FileResponse("app/static/checkout.html")

    return app


# Application instance
app = create_app()
