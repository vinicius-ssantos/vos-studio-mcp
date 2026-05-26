"""Add asset_lock column to brand_kits for campaign visual system v2 (Issue #56).

Adds a nullable JSONB ``asset_lock`` column that holds the expanded campaign
visual constraints: registers (dominant/secondary/forbidden), materials,
environments, text policy, endcard policy, and reference asset IDs.

Backward-compatible: existing brand kits default to NULL (no asset lock).

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-05-26 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "brand_kits",
        sa.Column("asset_lock", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("brand_kits", "asset_lock")
