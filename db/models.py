"""SQLAlchemy ORM models for VOS Studio (ADR-0007, ADR-0020)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, MetaData, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from typing import Any

convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=convention)


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    industry: Mapped[str] = mapped_column(String(100), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(200))
    contact_email: Mapped[str | None] = mapped_column(String(254))
    notes: Mapped[str | None] = mapped_column(Text)
    webhook_url: Mapped[str | None] = mapped_column(String(2048))  # outbound job notifications
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    brand_kits: Mapped[list["BrandKit"]] = relationship(back_populates="client")
    sprints: Mapped[list["Sprint"]] = relationship(back_populates="client")


class BrandKit(Base):
    __tablename__ = "brand_kits"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    identity: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    visual: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    restrictions: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    performance_memory: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    client: Mapped["Client"] = relationship(back_populates="brand_kits")
    sprints: Mapped[list["Sprint"]] = relationship(back_populates="brand_kit")


class Sprint(Base):
    __tablename__ = "sprints"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    brand_kit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brand_kits.id", ondelete="RESTRICT"), nullable=False
    )
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    campaign_objective: Mapped[str] = mapped_column(Text, nullable=False)
    target_audience: Mapped[str] = mapped_column(Text, nullable=False)
    brief: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(String(30), nullable=False, default="dashboard_manual")
    max_spend_usd: Mapped[float] = mapped_column(Float, nullable=False)
    max_images: Mapped[int | None] = mapped_column(Integer)
    max_videos: Mapped[int | None] = mapped_column(Integer)
    alert_threshold_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.8)
    spent_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sprint_status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    idempotency_key: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True
    )  # (client_id, idempotency_key) unique enforced by migration
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    client: Mapped["Client"] = relationship(back_populates="sprints")
    brand_kit: Mapped["BrandKit"] = relationship(back_populates="sprints")
    assets: Mapped[list["Asset"]] = relationship(back_populates="sprint")
    variant_groups: Mapped[list["VariantGroup"]] = relationship(back_populates="sprint")


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sprint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sprints.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    preset_version: Mapped[str] = mapped_column(String(50), nullable=False)
    storage_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    preview_url: Mapped[str | None] = mapped_column(Text)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    format: Mapped[str | None] = mapped_column(String(20))
    notes: Mapped[str | None] = mapped_column(Text)
    performance_score: Mapped[int | None] = mapped_column(Integer)
    performance_label: Mapped[str | None] = mapped_column(String(20))
    performance_notes: Mapped[str | None] = mapped_column(Text)
    provider_job_id: Mapped[str | None] = mapped_column(String(120), index=True)
    generation_status: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    storage_status: Mapped[str] = mapped_column(String(20), nullable=False, default="not_required")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("variants.id", ondelete="SET NULL"), nullable=True
    )

    sprint: Mapped["Sprint"] = relationship(back_populates="assets")
    variant: Mapped["Variant | None"] = relationship(back_populates="assets")


class VariantGroup(Base):
    __tablename__ = "variant_groups"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sprint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sprints.id", ondelete="CASCADE"), nullable=False
    )
    hypothesis: Mapped[str] = mapped_column(Text, nullable=False)
    variable: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    winner_variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("variants.id", ondelete="SET NULL"), nullable=True
    )
    concluded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    sprint: Mapped["Sprint"] = relationship(back_populates="variant_groups")
    variants: Mapped[list["Variant"]] = relationship(
        back_populates="group",
        foreign_keys="Variant.group_id",
    )


class Variant(Base):
    __tablename__ = "variants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("variant_groups.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    preset_version: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    group: Mapped["VariantGroup"] = relationship(
        back_populates="variants",
        foreign_keys=[group_id],
    )
    assets: Mapped[list["Asset"]] = relationship(back_populates="variant")


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    industry: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    format: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    objective: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    platform: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    prompt_template: Mapped[str] = mapped_column(Text, nullable=False)
    negative_prompt_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    preset_recommendations: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    avg_ctr: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_roas: Mapped[float | None] = mapped_column(Float, nullable=True)
    usage_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    performance_tier: Mapped[str] = mapped_column(
        String(20), nullable=False, default="experimental"
    )
    derived_from_sprint_ids: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    contributed_by: Mapped[str] = mapped_column(String(254), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AuditLog(Base):
    """Persistent audit trail for paid, external, delivery, approval, and asset-changing actions (ADR-0015)."""

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor: Mapped[str] = mapped_column(String(200), nullable=False)  # client_id or "system"
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    mode: Mapped[str | None] = mapped_column(String(50), nullable=True)
    cost_estimate_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    approval_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class ProviderUsageEvent(Base):
    """Per-provider cost ledger for global daily quota enforcement (ADR-0034)."""

    __tablename__ = "provider_usage_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    sprint_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sprints.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    estimated_usd: Mapped[float] = mapped_column(Float, nullable=False)
    actual_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class PerformanceRecord(Base):
    """Structured campaign performance record with distribution context and quantitative metrics (ADR-0025 Phase 2)."""

    __tablename__ = "performance_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sprint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sprints.id", ondelete="CASCADE"), nullable=False, index=True
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    brand_kit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brand_kits.id", ondelete="SET NULL"), nullable=True
    )
    # Distribution context
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    ad_account_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    campaign_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ad_set_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    start_date: Mapped[str] = mapped_column(String(20), nullable=False)  # ISO 8601 date
    end_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Quantitative metrics
    impressions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    clicks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ctr: Mapped[float | None] = mapped_column(Float, nullable=True)
    spend_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    conversions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    roas: Mapped[float | None] = mapped_column(Float, nullable=True)
    thumb_stop_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    hook_retention_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Outcome
    performance_label: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
