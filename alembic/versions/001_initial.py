"""Initial migration — create all tables.

Revision ID: 001
Revises:
Create Date: 2026-02-28

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Customers table ──
    op.create_table(
        "customers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("stripe_customer_id", sa.String(255), unique=True, nullable=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_customers_email", "customers", ["email"])
    op.create_index("ix_customers_stripe_customer_id", "customers", ["stripe_customer_id"])

    # ── Payments table ──
    op.create_table(
        "payments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("stripe_payment_intent_id", sa.String(255), unique=True, nullable=True),
        sa.Column("customer_id", UUID(as_uuid=True), sa.ForeignKey("customers.id"), nullable=True),
        sa.Column("amount", sa.Integer, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="usd"),
        sa.Column(
            "status",
            sa.Enum(
                "pending", "processing", "requires_action", "succeeded",
                "failed", "canceled", "refunded", "partially_refunded",
                name="payment_status",
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("payment_method_id", sa.String(255), nullable=True),
        sa.Column("client_secret", sa.String(255), nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("idempotency_key", sa.String(255), unique=True, nullable=True),
        sa.Column("amount_refunded", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_payments_stripe_payment_intent_id", "payments", ["stripe_payment_intent_id"])
    op.create_index("ix_payments_customer_id", "payments", ["customer_id"])
    op.create_index("ix_payments_status", "payments", ["status"])
    op.create_index("ix_payments_idempotency_key", "payments", ["idempotency_key"])

    # ── Refunds table ──
    op.create_table(
        "refunds",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("stripe_refund_id", sa.String(255), unique=True, nullable=True),
        sa.Column("payment_id", UUID(as_uuid=True), sa.ForeignKey("payments.id"), nullable=False),
        sa.Column("amount", sa.Integer, nullable=False),
        sa.Column(
            "reason",
            sa.Enum(
                "duplicate", "fraudulent", "requested_by_customer", "other",
                name="refund_reason",
            ),
            nullable=False,
            server_default="requested_by_customer",
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending", "succeeded", "failed", "canceled",
                name="refund_status",
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("idempotency_key", sa.String(255), unique=True, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_refunds_stripe_refund_id", "refunds", ["stripe_refund_id"])
    op.create_index("ix_refunds_payment_id", "refunds", ["payment_id"])
    op.create_index("ix_refunds_status", "refunds", ["status"])
    op.create_index("ix_refunds_idempotency_key", "refunds", ["idempotency_key"])

    # ── Receipts table ──
    op.create_table(
        "receipts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("payment_id", UUID(as_uuid=True), sa.ForeignKey("payments.id"), unique=True, nullable=False),
        sa.Column("receipt_number", sa.String(50), unique=True, nullable=False),
        sa.Column("pdf_data", sa.LargeBinary, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_receipts_payment_id", "receipts", ["payment_id"])
    op.create_index("ix_receipts_receipt_number", "receipts", ["receipt_number"])


def downgrade() -> None:
    op.drop_table("receipts")
    op.drop_table("refunds")
    op.drop_table("payments")
    op.drop_table("customers")
    op.execute("DROP TYPE IF EXISTS payment_status")
    op.execute("DROP TYPE IF EXISTS refund_reason")
    op.execute("DROP TYPE IF EXISTS refund_status")
