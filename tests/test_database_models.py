from sqlalchemy import CheckConstraint, create_mock_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.schema import UniqueConstraint

from app.database.base import Base
from app.database.models import (  # noqa: F401
    ClusterModel,
    ClusterRunModel,
    ClusterTrendModel,
    SourceItemModel,
)


def test_source_items_model_defines_expected_postgresql_schema() -> None:
    table = Base.metadata.tables["source_items"]

    assert isinstance(table.c.raw_payload.type, JSONB)
    assert table.c.processed_at.nullable is True
    assert table.c.embedding.nullable is True
    assert table.c.embedding.type.dim == 384
    assert table.c.embedding_model.nullable is True
    assert table.c.embedding_model.type.length == 255
    assert table.c.is_problem.nullable is True
    assert table.c.problem_confidence.nullable is True
    assert table.c.problem_reason.nullable is True
    assert table.c.problem_classifier.nullable is True
    assert table.c.problem_classifier.type.length == 255
    assert table.c.classified_at.nullable is True
    assert table.c.classified_at.type.timezone is True
    constraints = {
        constraint.name: str(constraint.sqltext)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert constraints["ck_source_items_embedding_requires_model"] == (
        "embedding IS NULL OR embedding_model IS NOT NULL"
    )
    assert constraints["ck_source_items_embedding_model_requires_embedding"] == (
        "embedding_model IS NULL OR embedding IS NOT NULL"
    )
    assert constraints["ck_source_items_problem_requires_metadata"] == (
        "is_problem IS NULL OR (problem_confidence IS NOT NULL AND problem_reason IS NOT NULL AND problem_classifier IS NOT NULL AND classified_at IS NOT NULL)"
    )
    assert constraints["ck_source_items_problem_confidence_range"] == (
        "problem_confidence IS NULL OR (problem_confidence >= 0 AND problem_confidence <= 1)"
    )
    assert constraints["ck_source_items_embedding_requires_problem"] == (
        "embedding IS NULL OR is_problem IS TRUE"
    )
    assert constraints["ck_source_items_non_problem_has_no_embedding"] == (
        "is_problem IS NULL OR is_problem = TRUE OR (embedding IS NULL AND embedding_model IS NULL)"
    )
    assert any(
        isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_source_items_source_external_id"
        and [column.name for column in constraint.columns] == ["source", "external_id"]
        for constraint in table.constraints
    )
    assert any(
        index.name == "ix_source_items_dedup_hash"
        and [column.name for column in index.columns] == ["dedup_hash"]
        for index in table.indexes
    )


def test_source_items_create_all_emits_postgresql_ddl() -> None:
    statements: list[str] = []

    def executor(sql, *multiparams, **params) -> None:
        statements.append(str(sql.compile(dialect=engine.dialect)))

    engine = create_mock_engine("postgresql+psycopg://postgres:postgres@localhost/unmeet", executor)
    Base.metadata.create_all(engine)

    ddl = "\n".join(statements)

    assert "CREATE TABLE source_items" in ddl
    assert "raw_payload JSONB" in ddl
    assert "embedding VECTOR(384)" in ddl
    assert "embedding_model VARCHAR(255)" in ddl
    assert "is_problem BOOLEAN" in ddl
    assert "problem_confidence FLOAT" in ddl
    assert "problem_reason TEXT" in ddl
    assert "problem_classifier VARCHAR(255)" in ddl
    assert "classified_at TIMESTAMP WITH TIME ZONE" in ddl
    assert "ck_source_items_embedding_requires_model" in ddl
    assert "ck_source_items_embedding_model_requires_embedding" in ddl
    assert "ck_source_items_problem_requires_metadata" in ddl
    assert "ck_source_items_problem_confidence_range" in ddl
    assert "ck_source_items_embedding_requires_problem" in ddl
    assert "ck_source_items_non_problem_has_no_embedding" in ddl
    assert "processed_at TIMESTAMP WITH TIME ZONE" in ddl
    assert "CONSTRAINT uq_source_items_source_external_id UNIQUE (source, external_id)" in ddl
    assert "CREATE INDEX ix_source_items_dedup_hash ON source_items (dedup_hash)" in ddl


def test_cluster_models_define_run_snapshot_schema_and_relations() -> None:
    run_table = Base.metadata.tables["cluster_runs"]
    cluster_table = Base.metadata.tables["clusters"]
    trend_table = Base.metadata.tables["cluster_trends"]
    association = Base.metadata.tables["cluster_source_items"]

    assert run_table.c.id.primary_key is True
    assert run_table.c.created_at.type.timezone is True
    assert run_table.c.created_at.server_default is not None
    assert run_table.c.embedding_model.nullable is False
    assert run_table.c.min_cluster_size.nullable is False
    assert run_table.c.min_samples.nullable is True
    assert run_table.c.metric.nullable is False
    assert cluster_table.c.id.primary_key is True
    assert cluster_table.c.id.autoincrement is True
    assert cluster_table.c.run_id.foreign_keys
    assert cluster_table.c.local_cluster_id.primary_key is False
    assert cluster_table.c.created_at.type.timezone is True
    assert cluster_table.c.updated_at.type.timezone is True
    assert cluster_table.c.created_at.server_default is not None
    assert cluster_table.c.updated_at.server_default is not None
    assert cluster_table.c.updated_at.onupdate is not None
    assert isinstance(cluster_table.c.keywords.type, JSONB)
    assert cluster_table.c.centroid.type.dim == 384
    assert any(
        isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_clusters_run_id_local_cluster_id"
        and [column.name for column in constraint.columns] == ["run_id", "local_cluster_id"]
        for constraint in cluster_table.constraints
    )
    assert ClusterRunModel.clusters.property.back_populates == "run"
    assert ClusterModel.run.property.back_populates == "clusters"
    assert ClusterModel.source_items.property.secondary is association
    assert trend_table.c.run_id.foreign_keys
    assert trend_table.c.current_cluster_id.foreign_keys
    assert trend_table.c.previous_cluster_id.nullable is True
    assert trend_table.c.status.type.length == 20
    assert any(
        isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_cluster_trends_run_current_cluster"
        and [column.name for column in constraint.columns] == ["run_id", "current_cluster_id"]
        for constraint in trend_table.constraints
    )
    assert ClusterTrendModel.__tablename__ == "cluster_trends"
