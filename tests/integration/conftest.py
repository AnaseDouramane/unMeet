"""Fixtures for tests that need a real PostgreSQL + pgvector database.

Set ``TEST_DATABASE_URL`` (for example
``postgresql+psycopg://postgres@127.0.0.1:5432/unmeet_test``) to run them. The database is
reset to an empty schema and migrated to head for every test module.
"""

import os
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

pytestmark = pytest.mark.integration


def _reset_schema(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))


@pytest.fixture(scope="module")
def migrated_engine() -> Iterator[Engine]:
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not set")
    engine = create_engine(TEST_DATABASE_URL, future=True)
    _reset_schema(engine)
    config = Config("alembic.ini")
    config.attributes["database_url"] = TEST_DATABASE_URL
    command.upgrade(config, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(migrated_engine: Engine) -> Iterator[sessionmaker[Session]]:
    with migrated_engine.begin() as connection:
        tables = connection.execute(
            text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                "AND tablename <> 'alembic_version'"
            )
        ).scalars()
        names = ", ".join(f'"{name}"' for name in tables)
        if names:
            connection.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    yield sessionmaker(bind=migrated_engine, autoflush=False, autocommit=False)

