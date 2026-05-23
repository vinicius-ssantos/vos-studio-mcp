"""Split storage_status from generation_status on assets (ADR-0031, issue #18).

Revision ID: b5c6d7e8f9a0
Revises: a3b4c5d6e7f8
Create Date: 2026-05-23 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b5c6d7e8f9a0"
down_revision: Union[str, None] = "a3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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

    # Grant SELECT/UPDATE on the new column so RLS policies and the
    # application role can read and write it.
    op.execute("GRANT SELECT, UPDATE (storage_status) ON assets TO vos_app")


def downgrade() -> None:
    op.drop_column("assets", "storage_status")
