"""Add prompt_templates table for cross-client prompt library (ADR-0029).

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-05-22 14:01:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a3b4c5d6e7f8"
down_revision: str | None = "f2a3b4c5d6e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "prompt_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        # Classification arrays stored as JSONB
        sa.Column("industry", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("format", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("objective", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("platform", postgresql.JSONB, nullable=False, server_default="[]"),
        # Template content
        sa.Column("prompt_template", sa.Text, nullable=False),
        sa.Column("negative_prompt_template", sa.Text, nullable=True),
        sa.Column(
            "preset_recommendations", postgresql.JSONB, nullable=False, server_default="[]"
        ),
        # Performance signal
        sa.Column("avg_ctr", sa.Float, nullable=True),
        sa.Column("avg_roas", sa.Float, nullable=True),
        sa.Column("usage_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "performance_tier",
            sa.String(20),
            nullable=False,
            server_default="experimental",
        ),
        # Provenance
        sa.Column(
            "derived_from_sprint_ids", postgresql.JSONB, nullable=False, server_default="[]"
        ),
        sa.Column("contributed_by", sa.String(254), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_prompt_templates_performance_tier", "prompt_templates", ["performance_tier"])


def downgrade() -> None:
    op.drop_table("prompt_templates")
