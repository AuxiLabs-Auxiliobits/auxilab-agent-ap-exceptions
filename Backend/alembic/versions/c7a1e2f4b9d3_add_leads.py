"""add leads (contact-form sales/support leads)

Revision ID: c7a1e2f4b9d3
Revises: b2d9f1e6c047
Create Date: 2026-06-19 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c7a1e2f4b9d3'
down_revision: Union[str, Sequence[str], None] = 'b2d9f1e6c047'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "leads",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("intent", sa.String(length=32), nullable=False, server_default="general"),
        sa.Column("subject", sa.String(length=200), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="new"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_leads_email", "leads", ["email"])
    op.create_index("ix_leads_intent", "leads", ["intent"])
    op.create_index("ix_leads_status", "leads", ["status"])


def downgrade() -> None:
    op.drop_index("ix_leads_status", table_name="leads")
    op.drop_index("ix_leads_intent", table_name="leads")
    op.drop_index("ix_leads_email", table_name="leads")
    op.drop_table("leads")
