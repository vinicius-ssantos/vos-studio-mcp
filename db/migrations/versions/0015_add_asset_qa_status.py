"""Add qa_status column to assets (Issue #57).

Revision ID: a1b2c3d4e5f6
Revises: f6a7b8c9d0e1
Create Date: 2026-05-27
"""

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "assets",
        sa.Column("qa_status", sa.String(20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("assets", "qa_status")
