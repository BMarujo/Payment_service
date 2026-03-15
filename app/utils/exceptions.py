"""
Custom exceptions and global exception handlers for RFC 7807 Problem Details.
"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError


# ── Custom Exception Classes ─────────────────────────


class PaymentServiceError(Exception):
    """Base exception for the payment service."""

    def __init__(self, detail: str, status_code: int = 500):
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


class NotFoundError(PaymentServiceError):
    """Resource not found."""

    def __init__(self, resource: str, resource_id: str):
        super().__init__(
            detail=f"{resource} with id '{resource_id}' not found",
            status_code=404,
        )
        self.resource = resource
        self.resource_id = resource_id


class PaymentError(PaymentServiceError):
    """Payment processing error."""

    def __init__(self, detail: str):
        super().__init__(detail=detail, status_code=422)


class RefundError(PaymentServiceError):
    """Refund processing error."""

    def __init__(self, detail: str):
        super().__init__(detail=detail, status_code=422)


class AuthenticationError(PaymentServiceError):
    """Authentication failure."""

    def __init__(self, detail: str = "Invalid or missing API key"):
        super().__init__(detail=detail, status_code=401)


class RateLimitError(PaymentServiceError):
    """Rate limit exceeded."""

    def __init__(self):
        super().__init__(
            detail="Rate limit exceeded. Please try again later.",
            status_code=429,
        )


class IdempotencyError(PaymentServiceError):
    """Idempotency conflict."""

    def __init__(self, detail: str = "Idempotency key already used with different parameters"):
        super().__init__(detail=detail, status_code=409)


# ── RFC 7807 Response Builder ────────────────────────


def _problem_response(
    status_code: int,
    title: str,
    detail: str,
    instance: str | None = None,
    error_type: str = "about:blank",
) -> JSONResponse:
    """Build an RFC 7807 Problem Details JSON response."""
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "type": error_type,
                "title": title,
                "status": status_code,
                "detail": detail,
                "instance": instance,
            }
        },
    )


# ── Global Exception Handlers ───────────────────────


def register_exception_handlers(app: FastAPI) -> None:
    """Register all global exception handlers on the FastAPI app."""

    @app.exception_handler(PaymentServiceError)
    async def payment_service_error_handler(
        request: Request, exc: PaymentServiceError
    ) -> JSONResponse:
        return _problem_response(
            status_code=exc.status_code,
            title=type(exc).__name__,
            detail=exc.detail,
            instance=str(request.url),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = exc.errors()
        detail = "; ".join(
            f"{'.'.join(str(loc) for loc in e['loc'])}: {e['msg']}" for e in errors
        )
        return _problem_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            title="Validation Error",
            detail=detail,
            instance=str(request.url),
            error_type="validation_error",
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        return _problem_response(
            status_code=500,
            title="Internal Server Error",
            detail="An unexpected error occurred. Please try again later.",
            instance=str(request.url),
        )
