"""Add provider job fields to assets.

Revision ID: e1f2a3b4c5d6
Revises: d7e8f9a0b1c2
Create Date: 2026-05-22 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, None] = "d7e8f9a0b1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("assets", sa.Column("provider_job_id", sa.String(120), nullable=True))
    op.add_column(
        "assets",
        sa.Column(
            "generation_status",
            sa.String(20),
            nullable=False,
            server_default="manual",
        ),
    )
    # Allow storage_url to be NULL for pending (not yet generated) assets
    op.alter_column("assets", "storage_url", nullable=True)

    op.create_index("ix_assets_provider_job_id", "assets", ["provider_job_id"])


def downgrade() -> None:
    op.drop_index("ix_assets_provider_job_id", table_name="assets")
    op.alter_column("assets", "storage_url", nullable=False)
    op.drop_column("assets", "generation_status")
    op.drop_column("assets", "provider_job_id")
