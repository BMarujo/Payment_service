"""
Redis-backed sliding window rate limiter.
"""

import logging
import time
from typing import Optional

import redis.asyncio as redis

from app.config import get_settings

logger = logging.getLogger(__name__)


class RateLimiter:
    """Sliding window rate limiter backed by Redis."""

    def __init__(self) -> None:
        settings = get_settings()
        self._redis: Optional[redis.Redis] = None
        self._redis_url = settings.redis_url
        self._max_requests = settings.rate_limit_requests
        self._window_seconds = settings.rate_limit_window_seconds

    async def _get_redis(self) -> redis.Redis:
        if self._redis is None:
            self._redis = redis.from_url(self._redis_url, decode_responses=True)
        return self._redis

    async def is_allowed(
        self,
        identifier: str,
        max_requests: Optional[int] = None,
        window_seconds: Optional[int] = None,
    ) -> tuple[bool, dict]:
        """
        Check if the request is allowed under the rate limit.

        Returns:
            (allowed, headers) where headers is a dict of rate-limit headers.
        """
        try:
            limit = max_requests or self._max_requests
            window = window_seconds or self._window_seconds
            r = await self._get_redis()
            key = f"rate_limit:{identifier}"
            now = time.time()
            window_start = now - window

            pipe = r.pipeline()
            # Remove old entries outside the window
            pipe.zremrangebyscore(key, 0, window_start)
            # Add current request
            pipe.zadd(key, {str(now): now})
            # Count requests in window
            pipe.zcard(key)
            # Set expiry on the key
            pipe.expire(key, window)
            results = await pipe.execute()

            request_count = results[2]
            remaining = max(0, limit - request_count)
            allowed = request_count <= limit

            headers = {
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": str(remaining),
                "X-RateLimit-Reset": str(int(now + window)),
            }

            if not allowed:
                logger.warning(f"Rate limit exceeded for: {identifier}")

            return allowed, headers

        except Exception as e:
            logger.warning(f"Redis error (rate limiter): {e}, allowing request")
            # Fail open — don't block requests if Redis is down
            return True, {
                "X-RateLimit-Limit": str(max_requests or self._max_requests),
                "X-RateLimit-Remaining": "unknown",
                "X-RateLimit-Reset": "unknown",
            }

    async def close(self) -> None:
        if self._redis:
            await self._redis.close()


# Singleton instance
rate_limiter = RateLimiter()
