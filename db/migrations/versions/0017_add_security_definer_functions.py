"""Add SECURITY DEFINER functions for cross-tenant asset/sprint lookups.

These functions are owned by the privileged migration runner (postgres /
Supabase service_role) and execute with BYPASSRLS, so the application can
use a non-privileged NOSUPERUSER/NOBYPASSRLS role for DATABASE_URL while
still resolving the asset owner before any RLS tenant context is available.

After this migration the application no longer needs SET row_security = off
on the main connection (ADR-0040).

Each function pins ``search_path = pg_catalog, public`` so a caller cannot
prepend a schema and shadow the unqualified ``assets`` / ``sprints`` /
``clients`` references — the standard hardening for SECURITY DEFINER
functions against search_path injection.

Revision ID: 3c4d5e6f7a8b
Revises: 2b3c4d5e6f7a
Create Date: 2026-06-04 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "3c4d5e6f7a8b"
down_revision: str | None = "2b3c4d5e6f7a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # vos_get_asset_client_id
    #   Returns the client_id that owns the given asset, bypassing RLS.
    #   Used by the provider webhook ingress to bootstrap tenant context.
    # ------------------------------------------------------------------
    op.execute("""
        CREATE OR REPLACE FUNCTION vos_get_asset_client_id(p_asset_id UUID)
        RETURNS UUID
        LANGUAGE sql
        SECURITY DEFINER
        STABLE
        SET search_path = pg_catalog, public
        AS $$
            SELECT s.client_id
            FROM assets a
            JOIN sprints s ON a.sprint_id = s.id
            WHERE a.id = p_asset_id
            LIMIT 1;
        $$
    """)

    # ------------------------------------------------------------------
    # vos_get_sprint_client_id
    #   Returns the client_id that owns the given sprint, bypassing RLS.
    # ------------------------------------------------------------------
    op.execute("""
        CREATE OR REPLACE FUNCTION vos_get_sprint_client_id(p_sprint_id UUID)
        RETURNS UUID
        LANGUAGE sql
        SECURITY DEFINER
        STABLE
        SET search_path = pg_catalog, public
        AS $$
            SELECT client_id FROM sprints WHERE id = p_sprint_id LIMIT 1;
        $$
    """)

    # ------------------------------------------------------------------
    # vos_get_asset_notification_context
    #   Returns (sprint_id, client_id, webhook_url) for an asset,
    #   bypassing RLS. Used by upload tasks to fan out webhook delivery.
    # ------------------------------------------------------------------
    op.execute("""
        CREATE OR REPLACE FUNCTION vos_get_asset_notification_context(p_asset_id UUID)
        RETURNS TABLE(sprint_id UUID, client_id UUID, webhook_url TEXT)
        LANGUAGE sql
        SECURITY DEFINER
        STABLE
        SET search_path = pg_catalog, public
        AS $$
            SELECT a.sprint_id, s.client_id, c.webhook_url
            FROM assets a
            JOIN sprints s ON a.sprint_id = s.id
            JOIN clients c ON s.client_id = c.id
            WHERE a.id = p_asset_id
            LIMIT 1;
        $$
    """)

    # ------------------------------------------------------------------
    # vos_get_asset_by_job_id
    #   Returns (asset_id, client_id) for the asset matching a
    #   provider_job_id, bypassing RLS.  Used by the provider webhook
    #   ingress (Higgsfield, Freepik, Magnific) to bootstrap tenant
    #   context before any client_id is known.
    # ------------------------------------------------------------------
    op.execute("""
        CREATE OR REPLACE FUNCTION vos_get_asset_by_job_id(p_job_id TEXT)
        RETURNS TABLE(asset_id UUID, client_id UUID)
        LANGUAGE sql
        SECURITY DEFINER
        STABLE
        SET search_path = pg_catalog, public
        AS $$
            SELECT a.id, s.client_id
            FROM assets a
            JOIN sprints s ON a.sprint_id = s.id
            WHERE a.provider_job_id = p_job_id
            LIMIT 1;
        $$
    """)

    # Grant EXECUTE to the non-privileged app role when it exists.
    # On Supabase production, grant to the Supabase authenticated role manually.
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'vos_app') THEN
                GRANT EXECUTE ON FUNCTION vos_get_asset_client_id(UUID) TO vos_app;
                GRANT EXECUTE ON FUNCTION vos_get_sprint_client_id(UUID) TO vos_app;
                GRANT EXECUTE ON FUNCTION vos_get_asset_notification_context(UUID) TO vos_app;
                GRANT EXECUTE ON FUNCTION vos_get_asset_by_job_id(TEXT) TO vos_app;
            END IF;
        END
        $$
    """)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS vos_get_asset_by_job_id(TEXT)")
    op.execute("DROP FUNCTION IF EXISTS vos_get_asset_notification_context(UUID)")
    op.execute("DROP FUNCTION IF EXISTS vos_get_sprint_client_id(UUID)")
    op.execute("DROP FUNCTION IF EXISTS vos_get_asset_client_id(UUID)")
