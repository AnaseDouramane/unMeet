from sqlalchemy.orm import Session, sessionmaker

from app.audit.log import AuditEvent, AuditLogRepository


def test_audit_events_round_trip_newest_first(session_factory: sessionmaker[Session]) -> None:
    repository = AuditLogRepository(session_factory)
    first = repository.record(
        AuditEvent("key:aa", "topic.create", "topic", "1", {"name": "CRM"}, request_id="r1")
    )
    repository.record(AuditEvent("ip:10.0.0.1", "topic.delete", "topic", "1"))

    assert first.id > 0 and first.created_at is not None
    events = repository.list()
    assert [e.action for e in events] == ["topic.delete", "topic.create"]
    assert events[1].details == {"name": "CRM"} and events[1].request_id == "r1"
    assert [e.action for e in repository.list(limit=1, offset=1)] == ["topic.create"]
