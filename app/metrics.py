"""
Business KPI metrics for the Payment Service.

All custom counters and histograms are defined here as a single source of truth.
Service code calls the helper functions to record events.
"""

import logging
import time
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger(__name__)

# ── Lazy metric handles (created once, reused) ──────────────
_meter = None
_payment_amount_counter = None
_payment_count_counter = None
_refund_amount_counter = None
_refund_count_counter = None
_checkout_counter = None
_customer_counter = None
_auth_duration_histogram = None
_auth_error_counter = None
_rate_limit_counter = None


def _get_meter():
    """Lazily create the meter so it works even if OTel is disabled."""
    global _meter
    if _meter is not None:
        return _meter
    try:
        from opentelemetry import metrics
        _meter = metrics.get_meter("payment-service.business", "1.0.0")
    except Exception:
        _meter = None
    return _meter


def _ensure_instruments():
    """Create all metric instruments once."""
    global _payment_amount_counter, _payment_count_counter
    global _refund_amount_counter, _refund_count_counter
    global _checkout_counter, _customer_counter
    global _auth_duration_histogram, _auth_error_counter
    global _rate_limit_counter

    if _payment_count_counter is not None:
        return  # Already initialised

    meter = _get_meter()
    if meter is None:
        return

    _payment_amount_counter = meter.create_counter(
        name="payment_total_amount",
        description="Total payment amount processed (in smallest currency unit)",
        unit="cents",
    )
    _payment_count_counter = meter.create_counter(
        name="payment_transactions_total",
        description="Total number of payment transactions",
        unit="1",
    )
    _refund_amount_counter = meter.create_counter(
        name="payment_refund_amount",
        description="Total refund amount (in smallest currency unit)",
        unit="cents",
    )
    _refund_count_counter = meter.create_counter(
        name="payment_refunds_total",
        description="Total number of refunds issued",
        unit="1",
    )
    _checkout_counter = meter.create_counter(
        name="checkout_sessions_total",
        description="Total checkout sessions by outcome",
        unit="1",
    )
    _customer_counter = meter.create_counter(
        name="customers_registered_total",
        description="Total customer registrations",
        unit="1",
    )
    _auth_duration_histogram = meter.create_histogram(
        name="auth_service_request_duration_seconds",
        description="EGS Auth Service request duration",
        unit="s",
    )
    _auth_error_counter = meter.create_counter(
        name="auth_service_errors_total",
        description="EGS Auth Service error count",
        unit="1",
    )
    _rate_limit_counter = meter.create_counter(
        name="rate_limit_exceeded_total",
        description="Requests rejected by rate limiter",
        unit="1",
    )


# ── Public helper functions ──────────────────────────────────


def record_payment(status: str, amount: int, currency: str) -> None:
    """Record a payment event (created, succeeded, failed, etc.)."""
    _ensure_instruments()
    if _payment_count_counter:
        _payment_count_counter.add(1, {"status": status, "currency": currency})
    if _payment_amount_counter and status == "succeeded":
        _payment_amount_counter.add(amount, {"currency": currency})


def record_refund(amount: int, currency: str) -> None:
    """Record a refund event."""
    _ensure_instruments()
    if _refund_count_counter:
        _refund_count_counter.add(1, {"currency": currency})
    if _refund_amount_counter:
        _refund_amount_counter.add(amount, {"currency": currency})


def record_checkout(status: str) -> None:
    """Record a checkout session event (created, complete, expired)."""
    _ensure_instruments()
    if _checkout_counter:
        _checkout_counter.add(1, {"status": status})


def record_customer_registered() -> None:
    """Record a new customer registration."""
    _ensure_instruments()
    if _customer_counter:
        _customer_counter.add(1)


def record_auth_duration(duration_seconds: float, success: bool) -> None:
    """Record an EGS Auth Service call duration."""
    _ensure_instruments()
    if _auth_duration_histogram:
        _auth_duration_histogram.record(
            duration_seconds, {"success": str(success).lower()}
        )
    if not success and _auth_error_counter:
        _auth_error_counter.add(1)


def record_rate_limit_exceeded(identifier: str) -> None:
    """Record a rate-limit rejection."""
    _ensure_instruments()
    if _rate_limit_counter:
        _rate_limit_counter.add(1)


@contextmanager
def measure_auth_call():
    """Context manager that measures EGS Auth call duration.

    Usage:
        with measure_auth_call() as ctx:
            result = await do_call()
            ctx["success"] = True
    """
    ctx = {"success": False}
    start = time.perf_counter()
    try:
        yield ctx
    finally:
        duration = time.perf_counter() - start
        record_auth_duration(duration, ctx.get("success", False))
