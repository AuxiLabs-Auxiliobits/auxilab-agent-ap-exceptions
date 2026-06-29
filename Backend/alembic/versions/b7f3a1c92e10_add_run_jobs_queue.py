"""add run_jobs durable execution queue

Revision ID: b7f3a1c92e10
Revises: 42a0cabaea47
Create Date: 2026-06-16 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b7f3a1c92e10'
down_revision: Union[str, Sequence[str], None] = '42a0cabaea47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the run_jobs durable run-execution queue table."""
    op.create_table(
        "run_jobs",
        sa.Column("run_id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("input_gz", sa.LargeBinary(), nullable=False),
        sa.Column("queue_status", sa.String(length=16), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("leased_by", sa.String(length=96), nullable=True),
        sa.Column("leased_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_run_jobs_tenant_id", "run_jobs", ["tenant_id"])
    op.create_index("ix_run_jobs_queue_status", "run_jobs", ["queue_status"])
    op.create_index("ix_run_jobs_created_at", "run_jobs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_run_jobs_created_at", table_name="run_jobs")
    op.drop_index("ix_run_jobs_queue_status", table_name="run_jobs")
    op.drop_index("ix_run_jobs_tenant_id", table_name="run_jobs")
    op.drop_table("run_jobs")
