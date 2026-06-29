"""add vendor_contacts (per-tenant vendor email directory)

Backs the per-tenant vendor → email directory (F1-5) the recipient resolver
consults, so a mixed-vendor upload routes each invoice to the correct vendor.

Revision ID: b2d9f1e6c047
Revises: a1c8e4f70d23
Create Date: 2026-06-18 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b2d9f1e6c047'
down_revision: Union[str, Sequence[str], None] = 'a1c8e4f70d23'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vendor_contacts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("vendor_key", sa.String(length=256), nullable=False),
        sa.Column("vendor_name", sa.String(length=256), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("contact_name", sa.String(length=256), nullable=True),
        sa.Column("updated_by", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "vendor_key", name="uq_vendor_contact_tenant_key"),
    )
    op.create_index("ix_vendor_contacts_tenant_id", "vendor_contacts", ["tenant_id"])
    op.create_index("ix_vendor_contacts_vendor_key", "vendor_contacts", ["vendor_key"])


def downgrade() -> None:
    op.drop_index("ix_vendor_contacts_vendor_key", table_name="vendor_contacts")
    op.drop_index("ix_vendor_contacts_tenant_id", table_name="vendor_contacts")
    op.drop_table("vendor_contacts")
