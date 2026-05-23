"""Add audit_logs table for operational traceability (ADR-0015).

Revision ID: c6d7e8f9a0b1
Revises: b5c6d7e8f9a0
Create Date: 2026-05-23 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c6d7e8f9a0b1"
down_revision: Union[str, None] = "b5c6d7e8f9a0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("actor", sa.String(200), nullable=False),
        sa.Column("action", sa.String(100), nullable=False, index=True),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.String(200), nullable=False, index=True),
        sa.Column("provider", sa.String(50), nullable=True),
        sa.Column("mode", sa.String(50), nullable=True),
        sa.Column("cost_estimate_usd", sa.Float, nullable=True),
        sa.Column("approval_status", sa.String(20), nullable=True),
        sa.Column("result", sa.String(20), nullable=False),
        sa.Column("failure_reason", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            index=True,
        ),
    )

    # No RLS on audit_logs — agency-wide table, not client-scoped.
    # Grant INSERT + SELECT to the app role so the server can write and read events.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'vos_app') THEN
                GRANT SELECT, INSERT ON audit_logs TO vos_app;
            END IF;
        END
        $$
        """
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
