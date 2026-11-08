from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

cluster_source_items = Table(
    "cluster_source_items",
    Base.metadata,
    Column("cluster_id", ForeignKey("clusters.id", ondelete="CASCADE"), primary_key=True),
    Column("source_item_id", ForeignKey("source_items.id", ondelete="CASCADE"), primary_key=True),
)


class SourceItemModel(Base):
    __tablename__ = "source_items"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_source_items_source_external_id"),
        Index("ix_source_items_dedup_hash", "dedup_hash"),
        CheckConstraint(
            "embedding IS NULL OR embedding_model IS NOT NULL",
            name="ck_source_items_embedding_requires_model",
        ),
        CheckConstraint(
            "embedding_model IS NULL OR embedding IS NOT NULL",
            name="ck_source_items_embedding_model_requires_embedding",
        ),
        CheckConstraint(
            "embedding_model IS NULL OR btrim(embedding_model) <> ''",
            name="ck_source_items_embedding_model_not_blank",
        ),
        CheckConstraint(
            "is_problem IS NULL OR (problem_confidence IS NOT NULL AND problem_reason IS NOT NULL AND problem_classifier IS NOT NULL AND classified_at IS NOT NULL)",
            name="ck_source_items_problem_requires_metadata",
        ),
        CheckConstraint(
            "is_problem IS NOT NULL OR (problem_confidence IS NULL AND problem_reason IS NULL AND problem_classifier IS NULL AND classified_at IS NULL)",
            name="ck_source_items_problem_metadata_requires_flag",
        ),
        CheckConstraint(
            "problem_confidence IS NULL OR (problem_confidence >= 0 AND problem_confidence <= 1)",
            name="ck_source_items_problem_confidence_range",
        ),
        CheckConstraint(
            "signal_severity IS NULL OR signal_severity BETWEEN 1 AND 3",
            name="ck_source_items_signal_severity_range",
        ),
        CheckConstraint(
            "embedding IS NULL OR is_problem IS TRUE",
            name="ck_source_items_embedding_requires_problem",
        ),
        CheckConstraint(
            "is_problem IS NULL OR is_problem = TRUE OR (embedding IS NULL AND embedding_model IS NULL)",
            name="ck_source_items_non_problem_has_no_embedding",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(255))
    source: Mapped[str] = mapped_column(String(50))
    raw_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    title: Mapped[str] = mapped_column(Text)
    clean_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str] = mapped_column(Text)
    clean_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str] = mapped_column(Text)
    document_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_problem: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    problem_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    problem_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    problem_classifier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    classified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    signal_intent: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pain_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    products_mentioned: Mapped[list[str] | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )
    signal_severity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(384), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dedup_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    engagement_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    clusters: Mapped[list["ClusterModel"]] = relationship(
        secondary=cluster_source_items, back_populates="source_items"
    )


class ClusterRunModel(Base):
    __tablename__ = "cluster_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    embedding_model: Mapped[str] = mapped_column(String(255), nullable=False)
    min_cluster_size: Mapped[int] = mapped_column(Integer, nullable=False)
    min_samples: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metric: Mapped[str] = mapped_column(String(50), nullable=False)
    clusters: Mapped[list["ClusterModel"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class ClusterModel(Base):
    __tablename__ = "clusters"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "local_cluster_id",
            name="uq_clusters_run_id_local_cluster_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("cluster_runs.id", ondelete="CASCADE"), nullable=False
    )
    local_cluster_id: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(Text)
    keywords: Mapped[list[str]] = mapped_column(JSONB)
    centroid: Mapped[list[float]] = mapped_column(Vector(384))
    document_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    run: Mapped[ClusterRunModel] = relationship(back_populates="clusters")
    source_items: Mapped[list[SourceItemModel]] = relationship(
        secondary=cluster_source_items, back_populates="clusters"
    )


class ClusterTrendModel(Base):
    __tablename__ = "cluster_trends"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "current_cluster_id",
            name="uq_cluster_trends_run_current_cluster",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("cluster_runs.id", ondelete="CASCADE"), nullable=False
    )
    current_cluster_id: Mapped[int] = mapped_column(
        ForeignKey("clusters.id", ondelete="CASCADE"), nullable=False
    )
    previous_cluster_id: Mapped[int | None] = mapped_column(
        ForeignKey("clusters.id", ondelete="SET NULL"), nullable=True
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)
    current_count: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_count: Mapped[int] = mapped_column(Integer, nullable=False)
    absolute_change: Mapped[int] = mapped_column(Integer, nullable=False)
    growth_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    similarity: Mapped[float | None] = mapped_column(Float, nullable=True)


class TrackedTopicModel(Base):
    """A saved signal search that is re-run on new data and delivered to a webhook."""

    __tablename__ = "tracked_topics"
    __table_args__ = (
        UniqueConstraint("name", name="uq_tracked_topics_name"),
        CheckConstraint(
            "min_severity IS NULL OR min_severity BETWEEN 1 AND 3",
            name="ck_tracked_topics_min_severity_range",
        ),
        CheckConstraint(
            "max_distance > 0 AND max_distance <= 2",
            name="ck_tracked_topics_max_distance_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    intents: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    products: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    sources: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    min_severity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_distance: Mapped[float] = mapped_column(Float, nullable=False, default=0.6)
    webhook_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class SignalTopicMatchModel(Base):
    """Why a classified item is relevant to a tracked topic, in the model's words."""

    __tablename__ = "signal_topic_matches"
    __table_args__ = (Index("ix_signal_topic_matches_topic_id", "topic_id"),)

    source_item_id: Mapped[int] = mapped_column(
        ForeignKey("source_items.id", ondelete="CASCADE"), primary_key=True
    )
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("tracked_topics.id", ondelete="CASCADE"), primary_key=True
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SourceCursorModel(Base):
    """High-water mark of what a connector already ingested (for example per subreddit)."""

    __tablename__ = "source_cursors"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AuditLogModel(Base):
    """Append-only record of a write: who (a hashed API-key id or IP), what, to which resource."""

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_created_at", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class LlmUsageModel(Base):
    """Tokens and estimated cost of one LLM call (cost is NULL when no prices are configured)."""

    __tablename__ = "llm_usage"
    __table_args__ = (Index("ix_llm_usage_created_at", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
