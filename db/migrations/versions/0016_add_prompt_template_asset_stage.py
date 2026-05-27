"""Add asset_stage tag array to prompt_templates (ADR-0029).

Enables search_library and promote_to_library to filter/tag templates by the
VOS production stage they are best suited for (stage_0 → final, repair).

Revision ID: 2b3c4d5e6f7a
Revises: 1a2b3c4d5e6f
Create Date: 2026-05-27
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "2b3c4d5e6f7a"
down_revision = "1a2b3c4d5e6f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "prompt_templates",
        sa.Column(
            "asset_stage",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("prompt_templates", "asset_stage")
