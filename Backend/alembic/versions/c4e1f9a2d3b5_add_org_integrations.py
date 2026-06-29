"""add org_integrations (per-org BYOK config)

Revision ID: c4e1f9a2d3b5
Revises: b7f3a1c92e10
Create Date: 2026-06-16 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c4e1f9a2d3b5'
down_revision: Union[str, Sequence[str], None] = 'b7f3a1c92e10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the per-org integration config table (encrypted secrets)."""
    op.create_table(
        "org_integrations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("secret_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("configured", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by", sa.String(length=256), nullable=True),
        sa.Column("updated_by", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "kind", name="uq_org_integration_tenant_kind"),
    )
    op.create_index("ix_org_integrations_tenant_id", "org_integrations", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_org_integrations_tenant_id", table_name="org_integrations")
    op.drop_table("org_integrations")
