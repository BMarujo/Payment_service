"""
Aggregated v1 API router — combines all endpoint sub-routers.
"""

from fastapi import APIRouter

from app.api.v1 import payments, customers, refunds, webhooks, api_keys, checkout, auth

router = APIRouter(prefix="/api/v1")

router.include_router(checkout.router)
router.include_router(payments.router)
router.include_router(customers.router)
router.include_router(refunds.router)
router.include_router(webhooks.router)
router.include_router(api_keys.router)
router.include_router(auth.router)
