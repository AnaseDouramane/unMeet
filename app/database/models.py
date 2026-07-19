from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Column,
    DateTime,
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
    embedding: Mapped[list[float] | None] = mapped_column(Vector(384), nullable=True)
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
