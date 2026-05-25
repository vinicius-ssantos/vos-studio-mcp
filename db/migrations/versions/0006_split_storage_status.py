"""Split storage_status from generation_status on assets (ADR-0031, issue #18).

Revision ID: b5c6d7e8f9a0
Revises: a3b4c5d6e7f8
Create Date: 2026-05-23 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b5c6d7e8f9a0"
down_revision: str | None = "a3b4c5d6e7f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "assets",
        sa.Column(
            "storage_status",
            sa.String(20),
            nullable=False,
            server_default="not_required",
        ),
    )
    # Back-fill: existing assets that already have a storage_url were
    # successfully uploaded before this column existed — mark them stored.
    op.execute(
        "UPDATE assets SET storage_status = 'stored' WHERE storage_url IS NOT NULL"
    )

    # Grant SELECT/UPDATE on the new column to the app role — conditional so
    # the migration succeeds in fresh CI environments where vos_app is created
    # after migrations run. In production the role exists and the grant applies.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'vos_app') THEN
                GRANT SELECT, UPDATE (storage_status) ON assets TO vos_app;
            END IF;
        END
        $$
        """
    )


def downgrade() -> None:
    op.drop_column("assets", "storage_status")
