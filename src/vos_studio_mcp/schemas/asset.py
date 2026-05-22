"""Asset schemas."""

from pydantic import BaseModel


class AssetInput(BaseModel):
    sprint_id: str
    provider: str
    prompt_version: str
    preset_version: str
    storage_url: str
    preview_url: str | None = None
    width: int | None = None
    height: int | None = None
    format: str | None = None
    notes: str | None = None


class AssetReference(BaseModel):
    asset_id: str
    storage_url: str
    preview_url: str | None = None


class AssetResponse(BaseModel):
    status: str
    asset_id: str
    sprint_id: str
    summary: str
    next_action: str
