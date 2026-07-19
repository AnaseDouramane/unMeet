from sqlalchemy import create_mock_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.schema import UniqueConstraint

from app.database.base import Base
from app.database.models import ClusterModel, ClusterRunModel, SourceItemModel  # noqa: F401


def test_source_items_model_defines_expected_postgresql_schema() -> None:
    table = Base.metadata.tables["source_items"]

    assert isinstance(table.c.raw_payload.type, JSONB)
    assert table.c.processed_at.nullable is True
    assert table.c.embedding.nullable is True
    assert table.c.embedding.type.dim == 384
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
    assert "processed_at TIMESTAMP WITH TIME ZONE" in ddl
    assert "CONSTRAINT uq_source_items_source_external_id UNIQUE (source, external_id)" in ddl
    assert "CREATE INDEX ix_source_items_dedup_hash ON source_items (dedup_hash)" in ddl


def test_cluster_models_define_run_snapshot_schema_and_relations() -> None:
    run_table = Base.metadata.tables["cluster_runs"]
    cluster_table = Base.metadata.tables["clusters"]
    association = Base.metadata.tables["cluster_source_items"]

    assert run_table.c.id.primary_key is True
    assert run_table.c.created_at.type.timezone is True
    assert run_table.c.created_at.server_default is not None
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
