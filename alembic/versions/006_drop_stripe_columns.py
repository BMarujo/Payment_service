"""Drop Stripe-specific columns from payments, customers, and refunds.

Revision ID: 006_drop_stripe
Revises: d06d205ef83f
Create Date: 2026-03-15
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "006_drop_stripe"
down_revision = "d06d205ef83f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Payments: drop stripe_payment_intent_id, client_secret, payment_method_id
    op.drop_index("ix_payments_stripe_payment_intent_id", table_name="payments", if_exists=True)
    op.drop_column("payments", "stripe_payment_intent_id")
    op.drop_column("payments", "client_secret")
    op.drop_column("payments", "payment_method_id")

    # Customers: drop stripe_customer_id
    op.drop_index("ix_customers_stripe_customer_id", table_name="customers", if_exists=True)
    op.drop_column("customers", "stripe_customer_id")

    # Refunds: drop stripe_refund_id
    op.drop_index("ix_refunds_stripe_refund_id", table_name="refunds", if_exists=True)
    op.drop_column("refunds", "stripe_refund_id")


def downgrade() -> None:
    # Refunds
    op.add_column("refunds", sa.Column("stripe_refund_id", sa.String(255), nullable=True))
    op.create_index("ix_refunds_stripe_refund_id", "refunds", ["stripe_refund_id"], unique=True)

    # Customers
    op.add_column("customers", sa.Column("stripe_customer_id", sa.String(255), nullable=True))
    op.create_index("ix_customers_stripe_customer_id", "customers", ["stripe_customer_id"], unique=True)

    # Payments
    op.add_column("payments", sa.Column("payment_method_id", sa.String(255), nullable=True))
    op.add_column("payments", sa.Column("client_secret", sa.String(255), nullable=True))
    op.add_column("payments", sa.Column("stripe_payment_intent_id", sa.String(255), nullable=True))
    op.create_index("ix_payments_stripe_payment_intent_id", "payments", ["stripe_payment_intent_id"], unique=True)
