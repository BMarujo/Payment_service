"""
Health check endpoint.
"""

import logging

from fastapi import APIRouter, status

from app.config import get_settings

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
