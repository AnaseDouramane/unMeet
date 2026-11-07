from sqlalchemy.orm import Session, sessionmaker

from app.ingestion.cursors import SourceCursorRepository


def test_cursors_round_trip_and_upsert(session_factory: sessionmaker[Session]) -> None:
    repository = SourceCursorRepository(session_factory)
    assert repository.get("reddit:sales") is None

    repository.set_many({"reddit:sales": "100.0", "reddit:saas": "50.0"})
    assert repository.get("reddit:sales") == "100.0"
    assert repository.get("reddit:saas") == "50.0"

    repository.set_many({"reddit:sales": "250.5"})
    assert repository.get("reddit:sales") == "250.5"
    assert repository.get("reddit:saas") == "50.0"
    repository.set_many({})  # no-op
