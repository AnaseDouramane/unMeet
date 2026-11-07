"""Bring the database schema to the latest migration.

Databases created before migrations existed (via ``Base.metadata.create_all``) already contain
the baseline tables: they are stamped at the baseline revision first, then upgraded.
"""

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from app.database.session import engine

BASELINE_REVISION = "03c0862e4ee0"


def alembic_config() -> Config:
    return Config("alembic.ini")


def main() -> None:
    config = alembic_config()
    table_names = set(inspect(engine).get_table_names())
    if "source_items" in table_names and "alembic_version" not in table_names:
        command.stamp(config, BASELINE_REVISION)
        print("Existing schema stamped at the baseline revision.")
    command.upgrade(config, "head")
    print("Database initialized.")


if __name__ == "__main__":
    main()
