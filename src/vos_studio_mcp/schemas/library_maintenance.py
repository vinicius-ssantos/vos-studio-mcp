"""Schemas for prompt library maintenance (ADR-0029)."""

from pydantic import BaseModel


class RefreshLibraryTiersResponse(BaseModel):
    status: str
    templates_updated: int
    tiers_changed: int
    summary: str
    next_action: str
