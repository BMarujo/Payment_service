"""
Admin API Key management endpoints.

All endpoints require the admin API key (ADMIN_API_KEY env var).
"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.api_key import (
    ApiKeyCreate,
    ApiKeyCreatedResponse,
    ApiKeyListResponse,
    ApiKeyResponse,
    ApiKeyUpdate,
)
from app.services.api_key_service import api_key_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/api-keys", tags=["API Keys"])


@router.post(
    "",
    response_model=ApiKeyCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new API key",
    description=(
        "Generate a new API key for a client/tenant. The raw key is returned "
        "**only in this response** — store it securely. It cannot be retrieved again.\n\n"
        "**Requires admin API key.**"
    ),
)
async def create_api_key(
    data: ApiKeyCreate,
    db: AsyncSession = Depends(get_db),
):
    return await api_key_service.create_api_key(db=db, data=data)


@router.get(
    "",
    response_model=ApiKeyListResponse,
    summary="List API keys",
    description="Retrieve a paginated list of all API keys. **Requires admin API key.**",
)
async def list_api_keys(
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Items to skip"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    db: AsyncSession = Depends(get_db),
):
    return await api_key_service.list_api_keys(
        db=db, limit=limit, offset=offset, is_active=is_active
    )


@router.get(
    "/{key_id}",
    response_model=ApiKeyResponse,
    summary="Get API key details",
    description="Retrieve details of a specific API key. **Requires admin API key.**",
)
async def get_api_key(
    key_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    return await api_key_service.get_api_key(db=db, key_id=key_id)


@router.put(
    "/{key_id}",
    response_model=ApiKeyResponse,
    summary="Update an API key",
    description=(
        "Update API key properties such as scopes, rate limits, or active status. "
        "**Requires admin API key.**"
    ),
)
async def update_api_key(
    key_id: UUID,
    data: ApiKeyUpdate,
    db: AsyncSession = Depends(get_db),
):
    return await api_key_service.update_api_key(db=db, key_id=key_id, data=data)


@router.delete(
    "/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke an API key",
    description="Permanently revoke an API key. The key will immediately stop working. **Requires admin API key.**",
)
async def revoke_api_key(
    key_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    await api_key_service.revoke_api_key(db=db, key_id=key_id)
    return None
