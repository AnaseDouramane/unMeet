from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.topics.repository import DuplicateTopicError, TopicRepository
from app.topics.schemas import TopicDefinition


def test_topics_round_trip_and_names_are_unique(session_factory: sessionmaker[Session]) -> None:
    repository = TopicRepository(session_factory)
    created = repository.create(
        TopicDefinition(
            name="CRM hygiene",
            description="duplicate or stale contacts in the CRM",
            intents=("competitor_complaint", "solution_search"),
            products=("HubSpot", "Salesforce"),
            min_severity=2,
            webhook_url="https://api.clay.com/v3/sources/webhook/abc",
        )
    )

    assert created.id > 0
    assert created.created_at is not None
    assert repository.get(created.id) == created
    assert repository.list() == (created,)
    with pytest.raises(DuplicateTopicError):
        repository.create(TopicDefinition(name="CRM hygiene", products=("Pipedrive",)))


def test_mark_delivered_and_delete(session_factory: sessionmaker[Session]) -> None:
    repository = TopicRepository(session_factory)
    topic = repository.create(TopicDefinition(name="Outbound", intents=("solution_search",)))
    moment = datetime(2026, 11, 7, 12, tzinfo=UTC)

    repository.mark_delivered(topic.id, moment)

    reloaded = repository.get(topic.id)
    assert reloaded is not None and reloaded.last_delivered_at == moment
    assert repository.delete(topic.id) is True
    assert repository.delete(topic.id) is False
    assert repository.get(topic.id) is None
