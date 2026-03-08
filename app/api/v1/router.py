"""
Aggregated v1 API router — combines all endpoint sub-routers.
"""

from fastapi import APIRouter

from app.api.v1 import payments, customers, webhooks, api_keys

router = APIRouter(prefix="/api/v1")

router.include_router(payments.router)
router.include_router(customers.router)
router.include_router(webhooks.router)
router.include_router(api_keys.router)


