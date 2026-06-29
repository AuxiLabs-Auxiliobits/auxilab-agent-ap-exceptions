"""add run_jobs.available_at (retry backoff)

Adds the earliest-claimable timestamp used to space out retries: a failed
attempt sets `available_at` into the future, and the worker skips a job until
that time passes. NULL means claimable immediately (the default for new jobs).

Revision ID: f5b2c9d31a40
Revises: e3a7c5d18f24
Create Date: 2026-06-17 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f5b2c9d31a40'
down_revision: Union[str, Sequence[str], None] = 'e3a7c5d18f24'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("run_jobs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("available_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("run_jobs", schema=None) as batch_op:
        batch_op.drop_column("available_at")
