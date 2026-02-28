"""
Stripe webhook handler.

Receives events from Stripe, verifies signature, and updates local state.
"""

import logging

from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.payment_service import payment_service
from app.services.stripe_service import stripe_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post(
    "/stripe",
    status_code=status.HTTP_200_OK,
    summary="Stripe webhook receiver",
    description=(
        "Receives and processes webhook events from Stripe. "
        "Verifies the webhook signature before processing. "
        "This endpoint should be configured in the Stripe Dashboard."
    ),
    include_in_schema=True,
)
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    stripe_signature: str = Header(..., alias="Stripe-Signature"),
):
    # Read raw body for signature verification
    payload = await request.body()

    # Verify signature and parse event
    event = stripe_service.verify_webhook_signature(payload, stripe_signature)

    event_type = event["type"]
    data_object = event["data"]["object"]

    logger.info(f"Processing webhook event: {event_type}")

    # Handle relevant events
    if event_type == "payment_intent.succeeded":
        await payment_service.update_payment_from_webhook(
            db=db,
            stripe_payment_intent_id=data_object["id"],
            stripe_status="succeeded",
        )

    elif event_type == "payment_intent.payment_failed":
        await payment_service.update_payment_from_webhook(
            db=db,
            stripe_payment_intent_id=data_object["id"],
            stripe_status="failed",
        )

    elif event_type == "payment_intent.canceled":
        await payment_service.update_payment_from_webhook(
            db=db,
            stripe_payment_intent_id=data_object["id"],
            stripe_status="canceled",
        )

    elif event_type == "payment_intent.processing":
        await payment_service.update_payment_from_webhook(
            db=db,
            stripe_payment_intent_id=data_object["id"],
            stripe_status="processing",
        )

    elif event_type in (
        "charge.refunded",
        "charge.refund.updated",
    ):
        # Refund events are handled at creation time; log for observability
        logger.info(f"Refund webhook event processed: {event_type}")

    else:
        logger.info(f"Unhandled webhook event type: {event_type}")

    return {"status": "received"}
