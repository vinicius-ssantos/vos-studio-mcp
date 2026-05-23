"""Add performance_records table for ADR-0025 Phase 2 structured metrics.

Revision ID: d7e8f9a0b1c2
Revises: c6d7e8f9a0b1
Create Date: 2026-05-23 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "d7e8f9a0b1c2"
down_revision: Union[str, None] = "c6d7e8f9a0b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "performance_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("asset_id", UUID(as_uuid=True), sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sprint_id", UUID(as_uuid=True), sa.ForeignKey("sprints.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("brand_kit_id", UUID(as_uuid=True), sa.ForeignKey("brand_kits.id", ondelete="SET NULL"), nullable=True),
        # Distribution context
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("ad_account_id", sa.String(200), nullable=True),
        sa.Column("campaign_id", sa.String(200), nullable=True),
        sa.Column("ad_set_id", sa.String(200), nullable=True),
        sa.Column("start_date", sa.String(20), nullable=False),
        sa.Column("end_date", sa.String(20), nullable=True),
        # Metrics
        sa.Column("impressions", sa.Integer, nullable=True),
        sa.Column("clicks", sa.Integer, nullable=True),
        sa.Column("ctr", sa.Float, nullable=True),
        sa.Column("spend_usd", sa.Float, nullable=True),
        sa.Column("conversions", sa.Integer, nullable=True),
        sa.Column("roas", sa.Float, nullable=True),
        sa.Column("thumb_stop_rate", sa.Float, nullable=True),
        sa.Column("hook_retention_rate", sa.Float, nullable=True),
        # Outcome
        sa.Column("performance_label", sa.String(20), nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_performance_records_asset_id", "performance_records", ["asset_id"])
    op.create_index("ix_performance_records_sprint_id", "performance_records", ["sprint_id"])
    op.create_index("ix_performance_records_client_id", "performance_records", ["client_id"])
    op.create_index("ix_performance_records_performance_label", "performance_records", ["performance_label"])
    op.create_index("ix_performance_records_recorded_at", "performance_records", ["recorded_at"])

    # RLS — same pattern as assets and sprints: filter by client_id
    op.execute("ALTER TABLE performance_records ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY performance_records_client_isolation ON performance_records
        USING (client_id::text = current_setting('app.current_client_id', TRUE))
    """)

    # Grant to app role — conditional (role may not exist in CI before grants step)
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'vos_app') THEN
                GRANT SELECT, INSERT ON performance_records TO vos_app;
                GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO vos_app;
            END IF;
        END
        $$
    """)


def downgrade() -> None:
    op.drop_table("performance_records")
