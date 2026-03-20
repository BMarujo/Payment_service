"""Make checkout_sessions.customer_id nullable

Revision ID: f3b6a9c2210a
Revises: 6fc1e8c0dd5c
Create Date: 2026-03-20

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f3b6a9c2210a"
down_revision: Union[str, None] = "6fc1e8c0dd5c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "checkout_sessions",
        "customer_id",
        existing_type=sa.UUID(),
        nullable=True,
    )


def downgrade() -> None:
    # Rows created by the new flow can have NULL customer_id before authorization.
    # Remove those transient rows to restore the old NOT NULL constraint.
    op.execute("DELETE FROM checkout_sessions WHERE customer_id IS NULL")
    op.alter_column(
        "checkout_sessions",
        "customer_id",
        existing_type=sa.UUID(),
        nullable=False,
    )
