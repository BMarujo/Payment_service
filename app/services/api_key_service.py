"""
API Key management service — generate, hash, validate, CRUD.
"""

import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional

import redis.asyncio as aioredis
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.api_key import ApiKey
from app.schemas.api_key import (
    ApiKeyCreate,
    ApiKeyCreatedResponse,
    ApiKeyListResponse,
    ApiKeyResponse,
    ApiKeyUpdate,
)
from app.utils.exceptions import NotFoundError, AuthenticationError

logger = logging.getLogger(__name__)

# Redis cache TTL for validated keys (5 minutes)
KEY_CACHE_TTL = 300
KEY_CACHE_PREFIX = "api_key:"


class ApiKeyService:
    """Manages API key lifecycle: creation, validation, revocation."""

    def __init__(self) -> None:
        settings = get_settings()
        self._redis: Optional[aioredis.Redis] = None
        self._redis_url = settings.redis_url

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._redis

    # ── Key Generation ───────────────────────────────

    @staticmethod
    def generate_raw_key() -> str:
        """Generate a new random API key with prefix."""
        random_part = secrets.token_hex(24)  # 48 hex chars
        return f"ps_live_{random_part}"

    @staticmethod
    def hash_key(raw_key: str) -> str:
        """Hash a raw API key with SHA-256."""
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    @staticmethod
    def get_key_prefix(raw_key: str) -> str:
        """Extract a display prefix from the raw key (e.g., 'ps_live_a1b2c3d4...')."""
        return raw_key[:16] + "..."

    # ── CRUD Operations ──────────────────────────────

    async def create_api_key(
        self, db: AsyncSession, data: ApiKeyCreate
    ) -> ApiKeyCreatedResponse:
        """
        Create a new API key. The raw key is returned ONLY in this response.
        """
        raw_key = self.generate_raw_key()
        key_hash = self.hash_key(raw_key)
        key_prefix = self.get_key_prefix(raw_key)

        api_key = ApiKey(
            key_hash=key_hash,
            key_prefix=key_prefix,
            client_name=data.client_name,
            description=data.description,
            scopes=data.scopes,
            rate_limit_requests=data.rate_limit_requests,
            rate_limit_window_seconds=data.rate_limit_window_seconds,
            expires_at=data.expires_at,
        )
        db.add(api_key)
        await db.flush()
        await db.refresh(api_key)

        logger.info(f"API key created: {key_prefix} for client '{data.client_name}'")

        return ApiKeyCreatedResponse(
            id=api_key.id,
            key_prefix=api_key.key_prefix,
            client_name=api_key.client_name,
            description=api_key.description,
            scopes=api_key.scopes,
            is_active=api_key.is_active,
            rate_limit_requests=api_key.rate_limit_requests,
            rate_limit_window_seconds=api_key.rate_limit_window_seconds,
            last_used_at=api_key.last_used_at,
            expires_at=api_key.expires_at,
            created_at=api_key.created_at,
            updated_at=api_key.updated_at,
            raw_key=raw_key,
        )

    async def get_api_key(self, db: AsyncSession, key_id: uuid.UUID) -> ApiKeyResponse:
        """Get API key details by ID."""
        api_key = await self._get_key_or_404(db, key_id)
        return self._to_response(api_key)

    async def list_api_keys(
        self,
        db: AsyncSession,
        limit: int = 20,
        offset: int = 0,
        is_active: Optional[bool] = None,
    ) -> ApiKeyListResponse:
        """List API keys with pagination."""
        query = select(ApiKey)
        if is_active is not None:
            query = query.where(ApiKey.is_active == is_active)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar_one()

        query = query.order_by(ApiKey.created_at.desc()).limit(limit).offset(offset)
        result = await db.execute(query)
        keys = result.scalars().all()

        return ApiKeyListResponse(
            items=[self._to_response(k) for k in keys],
            total=total,
            limit=limit,
            offset=offset,
            has_more=(offset + limit) < total,
        )

    async def update_api_key(
        self, db: AsyncSession, key_id: uuid.UUID, data: ApiKeyUpdate
    ) -> ApiKeyResponse:
        """Update an API key's properties."""
        api_key = await self._get_key_or_404(db, key_id)

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(api_key, field, value)

        await db.flush()
        await db.refresh(api_key)

        # Invalidate cache
        await self._invalidate_cache(api_key.key_hash)

        logger.info(f"API key updated: {api_key.key_prefix} fields={list(update_data.keys())}")
        return self._to_response(api_key)

    async def revoke_api_key(self, db: AsyncSession, key_id: uuid.UUID) -> None:
        """Revoke (soft-delete) an API key."""
        api_key = await self._get_key_or_404(db, key_id)
        api_key.is_active = False
        await db.flush()

        # Invalidate cache
        await self._invalidate_cache(api_key.key_hash)

        logger.info(f"API key revoked: {api_key.key_prefix} client='{api_key.client_name}'")

    # ── Validation (called on every authenticated request) ─

    async def validate_key(self, db: AsyncSession, raw_key: str) -> Optional[ApiKey]:
        """
        Validate an incoming API key.
        1. Hash the raw key
        2. Check Redis cache
        3. Fall back to DB lookup
        4. Verify is_active and not expired
        5. Update last_used_at
        Returns the ApiKey record or None if invalid.
        """
        key_hash = self.hash_key(raw_key)

        # Check Redis cache first
        cached = await self._get_cached_key(key_hash)
        if cached == "__invalid__":
            return None
        if cached == "__valid__":
            # Key is valid per cache, but we still need the full record for rate limits
            # Fetch from DB (this is rare as cache expires after 5 min)
            pass

        # DB lookup
        result = await db.execute(
            select(ApiKey).where(ApiKey.key_hash == key_hash)
        )
        api_key = result.scalar_one_or_none()

        if not api_key:
            await self._cache_key(key_hash, valid=False)
            return None

        # Check active status
        if not api_key.is_active:
            await self._cache_key(key_hash, valid=False)
            return None

        # Check expiration
        if api_key.expires_at and api_key.expires_at < datetime.now(timezone.utc):
            await self._cache_key(key_hash, valid=False)
            return None

        # Mark as valid in cache
        await self._cache_key(key_hash, valid=True)

        # Update last_used_at (fire-and-forget, don't block the request)
        try:
            api_key.last_used_at = datetime.now(timezone.utc)
            await db.flush()
        except Exception:
            pass  # Non-critical

        return api_key

    # ── Redis Cache ──────────────────────────────────

    async def _get_cached_key(self, key_hash: str) -> Optional[str]:
        try:
            r = await self._get_redis()
            return await r.get(f"{KEY_CACHE_PREFIX}{key_hash}")
        except Exception:
            return None

    async def _cache_key(self, key_hash: str, valid: bool) -> None:
        try:
            r = await self._get_redis()
            value = "__valid__" if valid else "__invalid__"
            await r.set(f"{KEY_CACHE_PREFIX}{key_hash}", value, ex=KEY_CACHE_TTL)
        except Exception:
            pass

    async def _invalidate_cache(self, key_hash: str) -> None:
        try:
            r = await self._get_redis()
            await r.delete(f"{KEY_CACHE_PREFIX}{key_hash}")
        except Exception:
            pass

    async def close(self) -> None:
        if self._redis:
            await self._redis.close()

    # ── Helpers ──────────────────────────────────────

    async def _get_key_or_404(self, db: AsyncSession, key_id: uuid.UUID) -> ApiKey:
        result = await db.execute(select(ApiKey).where(ApiKey.id == key_id))
        api_key = result.scalar_one_or_none()
        if not api_key:
            raise NotFoundError("ApiKey", str(key_id))
        return api_key

    @staticmethod
    def _to_response(api_key: ApiKey) -> ApiKeyResponse:
        return ApiKeyResponse(
            id=api_key.id,
            key_prefix=api_key.key_prefix,
            client_name=api_key.client_name,
            description=api_key.description,
            scopes=api_key.scopes,
            is_active=api_key.is_active,
            rate_limit_requests=api_key.rate_limit_requests,
            rate_limit_window_seconds=api_key.rate_limit_window_seconds,
            last_used_at=api_key.last_used_at,
            expires_at=api_key.expires_at,
            created_at=api_key.created_at,
            updated_at=api_key.updated_at,
        )


# Singleton
api_key_service = ApiKeyService()
