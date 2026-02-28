"""
Health check and readiness probe endpoints.
"""

import logging

import redis.asyncio as redis
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import get_settings
from app.database import async_session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    summary="Health check",
    description="Returns service health status. Used by container orchestrators.",
    response_model=dict,
    status_code=status.HTTP_200_OK,
)
async def health_check():
    """Basic liveness probe — always returns OK if the app is running."""
    return {
        "status": "healthy",
        "service": "payment-service",
        "version": get_settings().app_version,
    }


@router.get(
    "/ready",
    summary="Readiness probe",
    description="Checks connectivity to PostgreSQL and Redis.",
    status_code=status.HTTP_200_OK,
)
async def readiness_check():
    """Readiness probe — verifies DB and Redis connectivity."""
    settings = get_settings()
    checks = {}
    overall_healthy = True

    # Check PostgreSQL
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        checks["postgresql"] = "connected"
    except Exception as e:
        checks["postgresql"] = f"error: {str(e)}"
        overall_healthy = False

    # Check Redis
    try:
        r = redis.from_url(settings.redis_url, decode_responses=True)
        await r.ping()
        await r.close()
        checks["redis"] = "connected"
    except Exception as e:
        checks["redis"] = f"error: {str(e)}"
        overall_healthy = False

    response = {
        "status": "ready" if overall_healthy else "not_ready",
        "checks": checks,
    }

    if not overall_healthy:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=response,
        )
    return response
