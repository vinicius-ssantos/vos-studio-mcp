"""Add provider_usage_events table for global daily quota enforcement (ADR-0034, Issue #42).

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-05-24 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_usage_events",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column(
            "sprint_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sprints.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "client_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("estimated_usd", sa.Float(), nullable=False),
        sa.Column("actual_usd", sa.Float(), nullable=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_provider_usage_events_provider",
        "provider_usage_events",
        ["provider"],
    )
    op.create_index(
        "ix_provider_usage_events_sprint_id",
        "provider_usage_events",
        ["sprint_id"],
    )
    op.create_index(
        "ix_provider_usage_events_client_id",
        "provider_usage_events",
        ["client_id"],
    )
    op.create_index(
        "ix_provider_usage_events_recorded_at",
        "provider_usage_events",
        ["recorded_at"],
    )

    # RLS: clients may only read their own usage events; writes via service role
    op.execute("ALTER TABLE provider_usage_events ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY provider_usage_events_tenant_isolation
        ON provider_usage_events
        USING (client_id::text = current_setting('app.tenant_id', true))
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS provider_usage_events_tenant_isolation ON provider_usage_events")
    op.drop_index("ix_provider_usage_events_recorded_at", table_name="provider_usage_events")
    op.drop_index("ix_provider_usage_events_client_id", table_name="provider_usage_events")
    op.drop_index("ix_provider_usage_events_sprint_id", table_name="provider_usage_events")
    op.drop_index("ix_provider_usage_events_provider", table_name="provider_usage_events")
    op.drop_table("provider_usage_events")
