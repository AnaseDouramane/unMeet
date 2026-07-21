from __future__ import annotations

import sys

from sqlalchemy.exc import SQLAlchemyError

from app.database.models import ClusterTrendModel
from app.database.session import engine


def main() -> int:
    """Create the cluster trend snapshot table for databases created before this feature."""
    try:
        ClusterTrendModel.__table__.create(bind=engine, checkfirst=True)
    except SQLAlchemyError as error:
        print(f"Database migration error: {error}", file=sys.stderr)
        return 1
    print("Cluster trend schema is up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
