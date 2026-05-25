"""Create core entities: clients, brand_kits, sprints, assets.

Revision ID: c4f1a2b3d5e6
Revises:
Create Date: 2026-05-22 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c4f1a2b3d5e6"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "clients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("industry", sa.String(100), nullable=False),
        sa.Column("contact_name", sa.String(200)),
        sa.Column("contact_email", sa.String(254)),
        sa.Column("notes", sa.Text),
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

    op.create_table(
        "brand_kits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "client_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("version", sa.String(20), nullable=False, server_default="1.0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("identity", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("visual", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("restrictions", postgresql.JSONB, nullable=False, server_default="{}"),
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
    op.create_index("ix_brand_kits_client_id", "brand_kits", ["client_id"])

    op.create_table(
        "sprints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "client_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "brand_kit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brand_kits.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("product_name", sa.String(200), nullable=False),
        sa.Column("campaign_objective", sa.Text, nullable=False),
        sa.Column("target_audience", sa.Text, nullable=False),
        sa.Column("brief", sa.Text, nullable=False),
        sa.Column("mode", sa.String(30), nullable=False, server_default="dashboard_manual"),
        sa.Column("max_spend_usd", sa.Float, nullable=False),
        sa.Column("max_images", sa.Integer),
        sa.Column("max_videos", sa.Integer),
        sa.Column("alert_threshold_pct", sa.Float, nullable=False, server_default="0.8"),
        sa.Column("spent_usd", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("sprint_status", sa.String(20), nullable=False, server_default="open"),
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
    op.create_index("ix_sprints_client_id", "sprints", ["client_id"])
    op.create_index("ix_sprints_brand_kit_id", "sprints", ["brand_kit_id"])

    op.create_table(
        "assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "sprint_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sprints.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("prompt_version", sa.String(50), nullable=False),
        sa.Column("preset_version", sa.String(50), nullable=False),
        sa.Column("storage_url", sa.Text, nullable=False),
        sa.Column("preview_url", sa.Text),
        sa.Column("width", sa.Integer),
        sa.Column("height", sa.Integer),
        sa.Column("format", sa.String(20)),
        sa.Column("notes", sa.Text),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_assets_sprint_id", "assets", ["sprint_id"])

    # Enable Row Level Security on all tenant-scoped tables (ADR-0018)
    for table in ("clients", "brand_kits", "sprints", "assets"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

    op.execute("""
        CREATE POLICY clients_isolation ON clients
        USING (id = NULLIF(current_setting('app.current_client_id', TRUE), '')::uuid)
    """)
    op.execute("""
        CREATE POLICY brand_kits_isolation ON brand_kits
        USING (client_id = NULLIF(current_setting('app.current_client_id', TRUE), '')::uuid)
    """)
    op.execute("""
        CREATE POLICY sprints_isolation ON sprints
        USING (client_id = NULLIF(current_setting('app.current_client_id', TRUE), '')::uuid)
    """)
    op.execute("""
        CREATE POLICY assets_isolation ON assets
        USING (
            sprint_id IN (
                SELECT id FROM sprints
                WHERE client_id = NULLIF(current_setting('app.current_client_id', TRUE), '')::uuid
            )
        )
    """)


def downgrade() -> None:
    op.drop_table("assets")
    op.drop_table("sprints")
    op.drop_table("brand_kits")
    op.drop_table("clients")
