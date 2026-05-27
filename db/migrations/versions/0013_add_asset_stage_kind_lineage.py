"""Add asset stage, kind, lineage metadata (Issue #53).

Adds asset_stage, asset_kind, source_asset_id, approved_as_reference,
and is_final_delivery to the assets table.  These fields make assets
first-class creative artifacts with stage and lineage awareness.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-05-26 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # asset_stage: which VOS production stage this asset belongs to
    op.add_column(
        "assets",
        sa.Column("asset_stage", sa.String(length=20), nullable=True),
    )
    # asset_kind: generated | manual | upscaled
    op.add_column(
        "assets",
        sa.Column(
            "asset_kind",
            sa.String(length=20),
            nullable=False,
            server_default="manual",
        ),
    )
    # source_asset_id: FK to assets.id for lineage (repair variant, upscale, etc.)
    op.add_column(
        "assets",
        sa.Column("source_asset_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_assets_source_asset_id",
        "assets",
        "assets",
        ["source_asset_id"],
        ["id"],
        ondelete="SET NULL",
    )
    # approved_as_reference: true when QA-approved for use as reference in future sprints
    op.add_column(
        "assets",
        sa.Column(
            "approved_as_reference",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    # is_final_delivery: true when asset is the final deliverable for a sprint
    op.add_column(
        "assets",
        sa.Column(
            "is_final_delivery",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_constraint("fk_assets_source_asset_id", "assets", type_="foreignkey")
    op.drop_column("assets", "is_final_delivery")
    op.drop_column("assets", "approved_as_reference")
    op.drop_column("assets", "source_asset_id")
    op.drop_column("assets", "asset_kind")
    op.drop_column("assets", "asset_stage")
