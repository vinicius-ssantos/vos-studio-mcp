"""Add performance fields to brand_kits and assets.

Revision ID: d7e8f9a0b1c2
Revises: c4f1a2b3d5e6
Create Date: 2026-05-22 00:01:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d7e8f9a0b1c2"
down_revision: str | None = "c4f1a2b3d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "brand_kits",
        sa.Column(
            "performance_memory",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column("assets", sa.Column("performance_score", sa.Integer))
    op.add_column("assets", sa.Column("performance_label", sa.String(20)))
    op.add_column("assets", sa.Column("performance_notes", sa.Text))


def downgrade() -> None:
    op.drop_column("assets", "performance_notes")
    op.drop_column("assets", "performance_label")
    op.drop_column("assets", "performance_score")
    op.drop_column("brand_kits", "performance_memory")
