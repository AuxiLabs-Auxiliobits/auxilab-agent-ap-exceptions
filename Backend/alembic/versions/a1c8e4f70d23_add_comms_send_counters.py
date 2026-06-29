"""add comms_send_counters (distributed daily send cap)

Backs the per-(tenant, UTC day, recipient domain) live-send cap with a DB row +
atomic conditional increment, so the escalation-storm guard holds across
replicas instead of being a per-process counter.

Revision ID: a1c8e4f70d23
Revises: f5b2c9d31a40
Create Date: 2026-06-17 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1c8e4f70d23'
down_revision: Union[str, Sequence[str], None] = 'f5b2c9d31a40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "comms_send_counters",
        sa.Column("tenant_id", sa.String(length=128), primary_key=True),
        sa.Column("day_iso", sa.String(length=10), primary_key=True),
        sa.Column("domain", sa.String(length=255), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("comms_send_counters")
