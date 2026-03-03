"""
API Key service unit tests.
"""

import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.api_key import ApiKey
from app.services.api_key_service import ApiKeyService


class TestApiKeyService:
    """Unit tests for ApiKeyService."""

    @pytest.fixture
    def service(self):
        return ApiKeyService()

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.add = MagicMock()
        return db

    @pytest.fixture
    def active_api_key(self):
        return ApiKey(
            id=uuid.uuid4(),
            key_hash="abcdef1234567890" * 4,
            key_prefix="ps_live_a1b2c3d4...",
            client_name="Test Service",
            description="Test API key",
            scopes=["payments:read", "payments:write"],
            is_active=True,
            rate_limit_requests=200,
            rate_limit_window_seconds=60,
            last_used_at=None,
            expires_at=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def expired_api_key(self):
        return ApiKey(
            id=uuid.uuid4(),
            key_hash="deadbeef" * 8,
            key_prefix="ps_live_expired1...",
            client_name="Expired Service",
            is_active=True,
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    def test_generate_raw_key_format(self, service):
        """Generated keys should start with ps_live_ and be 56 chars total."""
        key = service.generate_raw_key()
        assert key.startswith("ps_live_")
        assert len(key) == 56  # 8 (prefix) + 48 (hex)

    def test_generate_raw_key_unique(self, service):
        """Each generated key should be unique."""
        keys = {service.generate_raw_key() for _ in range(100)}
        assert len(keys) == 100

    def test_hash_key_deterministic(self, service):
        """Same key should always produce the same hash."""
        key = "ps_live_abc123"
        hash1 = service.hash_key(key)
        hash2 = service.hash_key(key)
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256

    def test_hash_key_different_inputs(self, service):
        """Different keys should produce different hashes."""
        hash1 = service.hash_key("ps_live_key1")
        hash2 = service.hash_key("ps_live_key2")
        assert hash1 != hash2

    def test_get_key_prefix(self, service):
        """Prefix should show first 16 chars + ellipsis."""
        key = "ps_live_abcdef1234567890abcdef1234567890abcdef12345678"
        prefix = service.get_key_prefix(key)
        assert prefix == "ps_live_abcdef12..."
        assert len(prefix) == 19

    def test_to_response(self, service, active_api_key):
        """Model to response conversion should work correctly."""
        response = service._to_response(active_api_key)
        assert response.client_name == "Test Service"
        assert response.is_active is True
        assert response.scopes == ["payments:read", "payments:write"]

    @pytest.mark.asyncio
    async def test_get_api_key_not_found(self, service, mock_db):
        """Getting a non-existent key should raise NotFoundError."""
        from app.utils.exceptions import NotFoundError

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(NotFoundError):
            await service.get_api_key(mock_db, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_validate_key_inactive(self, service, mock_db, active_api_key):
        """Inactive keys should fail validation."""
        active_api_key.is_active = False

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = active_api_key
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch.object(service, '_get_cached_key', return_value=None):
            with patch.object(service, '_cache_key', return_value=None):
                result = await service.validate_key(mock_db, "ps_live_testkey")
                assert result is None

    @pytest.mark.asyncio
    async def test_validate_key_expired(self, service, mock_db, expired_api_key):
        """Expired keys should fail validation."""
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = expired_api_key
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch.object(service, '_get_cached_key', return_value=None):
            with patch.object(service, '_cache_key', return_value=None):
                result = await service.validate_key(mock_db, "ps_live_testkey")
                assert result is None
