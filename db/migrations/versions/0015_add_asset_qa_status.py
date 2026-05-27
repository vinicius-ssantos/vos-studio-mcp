"""Add qa_status column to assets (Issue #57).

Revision ID: 1a2b3c4d5e6f
Revises: f6a7b8c9d0e1
Create Date: 2026-05-27
"""

import sqlalchemy as sa
from alembic import op

revision: str = "1a2b3c4d5e6f"
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
