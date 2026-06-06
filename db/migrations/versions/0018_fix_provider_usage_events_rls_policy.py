"""Fix provider_usage_events RLS policy: align to app.current_client_id.

Migration 0011 created the tenant isolation policy keyed on ``app.tenant_id``,
but nothing in the application ever sets that variable — the app uses
``app.current_client_id`` consistently for all other tenant tables.  Under a
genuinely RLS-subject role the old policy denies every row, so callers were
routing through the privileged connection as a workaround.

This migration drops the old policy and recreates it using
``app.current_client_id``, matching the pattern on all other tenant tables.
The privileged connection is still used for cross-tenant aggregate queries
(daily budget totals); after this migration client-scoped reads can also use
the main role (ADR-0040 known follow-up, ADR-0023).

Revision ID: 4d5e6f7a8b9c
Revises: 3c4d5e6f7a8b
Create Date: 2026-06-06 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "4d5e6f7a8b9c"
down_revision: str | None = "3c4d5e6f7a8b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS provider_usage_events_tenant_isolation ON provider_usage_events"
    )
    op.execute(
        """
        CREATE POLICY provider_usage_events_tenant_isolation
        ON provider_usage_events
        USING (
            client_id = NULLIF(current_setting('app.current_client_id', TRUE), '')::uuid
        )
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS provider_usage_events_tenant_isolation ON provider_usage_events"
    )
    # Restore the original (broken) policy for clean rollback
    op.execute(
        """
        CREATE POLICY provider_usage_events_tenant_isolation
        ON provider_usage_events
        USING (client_id::text = current_setting('app.tenant_id', true))
        """
    )
