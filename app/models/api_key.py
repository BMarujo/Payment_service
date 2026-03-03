"""
API Key model — stores hashed API keys for multi-tenant authentication.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    Boolean,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.database import Base


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # The key is hashed (SHA-256) before storage — raw key is never stored
    key_hash = Column(String(64), unique=True, nullable=False, index=True)

    # First 8 characters of the raw key for identification (e.g., "ps_live_a1b2c3d4")
    key_prefix = Column(String(20), nullable=False)

    # Tenant identification
    client_name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)

    # Access control — list of allowed scopes
    # e.g., ["payments:read", "payments:write", "refunds:read", "refunds:write"]
    # Empty list or null = all scopes allowed
    scopes = Column(JSONB, nullable=True, default=list)

    # Status
    is_active = Column(Boolean, nullable=False, default=True)

    # Per-key rate limiting (overrides global defaults if set)
    rate_limit_requests = Column(Integer, nullable=True)
    rate_limit_window_seconds = Column(Integer, nullable=True)

    # Usage tracking
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    # Expiration (null = never expires)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return f"<ApiKey {self.key_prefix}... client={self.client_name} active={self.is_active}>"
