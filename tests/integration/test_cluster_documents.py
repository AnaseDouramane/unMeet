from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from app.clustering.schemas import ClusterableDocument
from app.clustering.service import DocumentCluster
from app.clustering.topic_labeling import TopicLabel
from app.database.repository import ClusterRepository, SourceItemRepository
from app.database.schemas import ClusterRunMetadata
from app.ingestion.schemas import SourceItem
from app.problem_detection.schemas import ProblemDetectionResult
from app.services.preprocessing import PreprocessingService
from tests.integration.test_database import MODEL, _unit


def test_cluster_documents_carry_the_verified_quote_and_newest_come_first(
    session_factory: sessionmaker[Session],
) -> None:
    items = SourceItemRepository(session_factory)
    saved = []
    for index, (quote, days) in enumerate([("first quote", 3), (None, 1), ("third quote", 2)]):
        item = SourceItem(
            external_id=f"c{index}",
            source="reddit",
            title=f"Title {index}",
            body="body",
            url=f"https://example.test/{index}",
            author="someone",
            published_at=datetime(2026, 11, 1, tzinfo=UTC) + timedelta(days=days),
            engagement_score=None,
            raw_payload={},
        )
        result = ProblemDetectionResult(True, 0.9, "r", "c", pain_quote=quote)
        saved.append(
            items.save(item, PreprocessingService().prepare(item), _unit(index), MODEL, result)
        )

    cluster = DocumentCluster(
        0,
        tuple(
            ClusterableDocument(
                s.id, s.source, s.external_id, s.document_text or "", _unit(i), MODEL
            )
            for i, s in enumerate(saved)
        ),
    )
    clusters = ClusterRepository(session_factory)
    run = clusters.save_run(
        [(cluster, TopicLabel(0, "Teams dedupe by hand", ("dedupe",)), _unit(0))],
        ClusterRunMetadata(MODEL, 2, 1, "euclidean"),
    )

    documents = clusters.get_documents_for_cluster(run.clusters[0].id, limit=10)

    assert [d.external_id for d in documents] == ["c0", "c2", "c1"]  # newest first
    assert [d.pain_quote for d in documents] == ["first quote", "third quote", None]
