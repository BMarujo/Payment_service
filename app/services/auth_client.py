"""
EGS Auth Service client — verifies Bearer tokens via the external Auth Service.

The Payment Service delegates all token validation to the EGS Auth Service
by calling POST /api/v1/auth/verify with the shared INTERNAL_SERVICE_KEY.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import httpx
from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class VerifiedUser:
    """Result of a successful token verification."""
    user_id: str
    email: str
    role: str


async def verify_token_with_auth_service(token: str) -> Optional[VerifiedUser]:
    """Call the EGS Auth Service /verify endpoint to validate a Bearer token.
    
    Returns a VerifiedUser if the token is valid, or None if invalid/expired.
    Raises httpx.HTTPError on network failures.
    """
    settings = get_settings()
    url = f"{settings.auth_service_url}/api/v1/auth/verify"

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            url,
            json={"token": token},
            headers={"X-Service-Auth": settings.internal_service_key},
        )

    if resp.status_code == 403:
        logger.error("EGS Auth Service rejected our INTERNAL_SERVICE_KEY (403).")
        return None

    if resp.status_code != 200:
        logger.warning("EGS Auth /verify returned status %s", resp.status_code)
        return None

    data = resp.json()

    if not data.get("valid"):
        return None

    return VerifiedUser(
        user_id=data.get("user_id", ""),
        email=data.get("email", ""),
        role=data.get("role", ""),
    )
