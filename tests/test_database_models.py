from sqlalchemy import create_mock_engine, inspect
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.schema import UniqueConstraint

from app.database.base import Base
from app.database.models import SourceItemModel  # noqa: F401


def test_source_items_model_defines_expected_postgresql_schema() -> None:
    table = Base.metadata.tables["source_items"]

    assert isinstance(table.c.raw_payload.type, JSONB)
    assert table.c.processed_at.nullable is True
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
    assert "processed_at TIMESTAMP WITH TIME ZONE" in ddl
    assert "CONSTRAINT uq_source_items_source_external_id UNIQUE (source, external_id)" in ddl
    assert "CREATE INDEX ix_source_items_dedup_hash ON source_items (dedup_hash)" in ddl
