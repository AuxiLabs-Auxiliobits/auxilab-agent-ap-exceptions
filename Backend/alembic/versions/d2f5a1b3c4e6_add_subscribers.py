"""add subscribers (newsletter list)

Revision ID: d2f5a1b3c4e6
Revises: c4e1f9a2d3b5
Create Date: 2026-06-17 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd2f5a1b3c4e6'
down_revision: Union[str, Sequence[str], None] = 'c4e1f9a2d3b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "subscribers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("unsubscribe_token", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("email", name="uq_subscribers_email"),
        sa.UniqueConstraint("unsubscribe_token", name="uq_subscribers_unsub_token"),
    )
    op.create_index("ix_subscribers_status", "subscribers", ["status"])


def downgrade() -> None:
    op.drop_index("ix_subscribers_status", table_name="subscribers")
    op.drop_table("subscribers")
