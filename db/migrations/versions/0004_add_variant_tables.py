"""Add variant_groups and variants tables for A/B testing (ADR-0027).

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-05-22 14:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "variant_groups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "sprint_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sprints.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("hypothesis", sa.Text, nullable=False),
        sa.Column("variable", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("winner_variant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("concluded_at", sa.DateTime(timezone=True), nullable=True),
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
    op.create_index("ix_variant_groups_sprint_id", "variant_groups", ["sprint_id"])

    op.create_table(
        "variants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "group_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("variant_groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("prompt_version", sa.String(50), nullable=False),
        sa.Column("preset_version", sa.String(50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_variants_group_id", "variants", ["group_id"])

    # Add winner FK after variants table exists
    op.create_foreign_key(
        "fk_variant_groups_winner_variant_id_variants",
        "variant_groups",
        "variants",
        ["winner_variant_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Add optional variant_id to assets
    op.add_column(
        "assets",
        sa.Column("variant_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_assets_variant_id_variants",
        "assets",
        "variants",
        ["variant_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_assets_variant_id", "assets", ["variant_id"])

    # RLS — variant_groups and variants are scoped via sprint → client
    for table in ("variant_groups", "variants"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

    op.execute("""
        CREATE POLICY variant_groups_isolation ON variant_groups
        USING (
            sprint_id IN (
                SELECT id FROM sprints
                WHERE client_id = NULLIF(current_setting('app.current_client_id', TRUE), '')::uuid
            )
        )
    """)
    op.execute("""
        CREATE POLICY variants_isolation ON variants
        USING (
            group_id IN (
                SELECT vg.id FROM variant_groups vg
                JOIN sprints s ON s.id = vg.sprint_id
                WHERE s.client_id = NULLIF(current_setting('app.current_client_id', TRUE), '')::uuid
            )
        )
    """)


def downgrade() -> None:
    op.drop_constraint("fk_assets_variant_id_variants", "assets", type_="foreignkey")
    op.drop_index("ix_assets_variant_id", table_name="assets")
    op.drop_column("assets", "variant_id")

    op.drop_constraint(
        "fk_variant_groups_winner_variant_id_variants", "variant_groups", type_="foreignkey"
    )
    op.drop_table("variants")
    op.drop_table("variant_groups")
