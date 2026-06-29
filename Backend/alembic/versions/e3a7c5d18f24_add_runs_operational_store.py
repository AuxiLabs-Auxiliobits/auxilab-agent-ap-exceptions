"""add runs operational store

The `runs` table is the operational run-store the API reads/writes on every
pipeline step (app/api/db_store.py) — distinct from the normalized analytical
tables. It existed only via create_all / supabase/schema.sql, so a deploy that
relied on `alembic upgrade head` had no run store. This migration makes
migrations the complete source of truth.

Revision ID: e3a7c5d18f24
Revises: d2f5a1b3c4e6
Create Date: 2026-06-17 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e3a7c5d18f24'
down_revision: Union[str, Sequence[str], None] = 'd2f5a1b3c4e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# jsonb on Postgres, json on SQLite — mirrors the Run.state column + schema.sql.
_STATE = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    """Create the operational `runs` table (one serialized RunState per row)."""
    op.create_table(
        "runs",
        sa.Column("run_id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("current_node", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rows_accepted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_quarantined", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("state", _STATE, nullable=False),
    )
    op.create_index("ix_runs_tenant_id", "runs", ["tenant_id"])
    op.create_index("ix_runs_status", "runs", ["status"])
    op.create_index("ix_runs_created_at", "runs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_runs_created_at", table_name="runs")
    op.drop_index("ix_runs_status", table_name="runs")
    op.drop_index("ix_runs_tenant_id", table_name="runs")
    op.drop_table("runs")
