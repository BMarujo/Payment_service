"""
Redis-backed idempotency middleware.

Clients can send an `Idempotency-Key` header on POST requests.
If the same key is reused, the cached response is returned without
re-processing the request.
"""

import hashlib
import json
import logging
from typing import Optional

import redis.asyncio as redis

from app.config import get_settings

logger = logging.getLogger(__name__)

# Cache TTL for idempotency keys (24 hours)
IDEMPOTENCY_TTL = 86400


class IdempotencyService:
    """Manages idempotency key storage in Redis."""

    def __init__(self) -> None:
        settings = get_settings()
        self._redis: Optional[redis.Redis] = None
        self._redis_url = settings.redis_url

    async def _get_redis(self) -> redis.Redis:
        if self._redis is None:
            self._redis = redis.from_url(self._redis_url, decode_responses=True)
        return self._redis

    def _make_key(self, idempotency_key: str) -> str:
        return f"idempotency:{idempotency_key}"

    async def get_cached_response(self, idempotency_key: str) -> Optional[dict]:
        """Return cached response for this idempotency key, or None."""
        try:
            r = await self._get_redis()
            data = await r.get(self._make_key(idempotency_key))
            if data:
                logger.info(f"Idempotency cache hit for key: {idempotency_key}")
                return json.loads(data)
        except Exception as e:
            logger.warning(f"Redis error (idempotency get): {e}")
        return None

    async def cache_response(
        self, idempotency_key: str, status_code: int, body: dict
    ) -> None:
        """Cache a response under the given idempotency key."""
        try:
            r = await self._get_redis()
            data = json.dumps({"status_code": status_code, "body": body})
            await r.set(
                self._make_key(idempotency_key), data, ex=IDEMPOTENCY_TTL
            )
            logger.info(f"Idempotency cache set for key: {idempotency_key}")
        except Exception as e:
            logger.warning(f"Redis error (idempotency set): {e}")

    async def close(self) -> None:
        if self._redis:
            await self._redis.close()


# Singleton instance
idempotency_service = IdempotencyService()
