"""add org_policies (per-tenant resolution rulebook)

Revision ID: d8b3f0a25c61
Revises: c7a1e2f4b9d3
Create Date: 2026-06-19 00:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd8b3f0a25c61'
down_revision: Union[str, Sequence[str], None] = 'c7a1e2f4b9d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "org_policies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("policy", sa.JSON(), nullable=False),
        sa.Column("updated_by", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", name="uq_org_policies_tenant"),
    )
    op.create_index("ix_org_policies_tenant_id", "org_policies", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_org_policies_tenant_id", table_name="org_policies")
    op.drop_table("org_policies")
