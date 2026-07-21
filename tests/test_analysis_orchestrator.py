from datetime import datetime, timezone

import pytest

from app.analysis.orchestrator import AnalysisOrchestrator
from app.clustering.schemas import ClusterMatch, ClusterTrend, ClusterableDocument
from app.clustering.service import ClusteringResult, DocumentCluster
from app.clustering.topic_labeling import TopicLabel
from app.database.schemas import (
    ClusterRunMetadata,
    PersistedCluster,
    PersistedClusterDetails,
    PersistedClusterRun,
    PersistedClusterRunDetails,
)

METADATA = ClusterRunMetadata("model-a", 5, None, "euclidean")
CREATED_AT = datetime(2026, 1, 2, tzinfo=timezone.utc)


def _document(document_id: int, value: float, model: str = "model-a") -> ClusterableDocument:
    return ClusterableDocument(
        id=document_id,
        source="hackernews",
        external_id=str(document_id),
        document_text=f"document {document_id}",
        embedding=tuple([value] * 384),
        embedding_model=model,
    )


def _cluster(cluster_id: int, *documents: ClusterableDocument) -> DocumentCluster:
    return DocumentCluster(cluster_id=cluster_id, documents=documents)


class FakeClusteringService:
    def __init__(self, result: ClusteringResult) -> None:
        self.result = result
        self.embedding_models: list[str] = []

    def cluster_documents_with_summary(self, embedding_model: str) -> ClusteringResult:
        self.embedding_models.append(embedding_model)
        return self.result


class FakeLabelingService:
    def __init__(self, error_cluster_id: int | None = None) -> None:
        self.error_cluster_id = error_cluster_id
        self.cluster_ids: list[int] = []

    def label_cluster(self, cluster: DocumentCluster) -> TopicLabel:
        self.cluster_ids.append(cluster.cluster_id)
        if cluster.cluster_id == self.error_cluster_id:
            raise ValueError("labeling failed")
        return TopicLabel(cluster.cluster_id, f"label-{cluster.cluster_id}", ("keyword",))


class FakeClusterRepository:
    def __init__(
        self,
        previous_run: PersistedClusterRunDetails | None = None,
        previous_clusters: tuple[PersistedClusterDetails, ...] = (),
    ) -> None:
        self.previous_run = previous_run
        self.previous_clusters = previous_clusters
        self.save_calls: list[tuple] = []
        self.trend_save_calls: list[tuple[int, tuple[ClusterTrend, ...]]] = []
        self.deleted_run_ids: list[int] = []
        self.compatibility_calls: list[tuple[ClusterRunMetadata, int]] = []
        self.cluster_run_ids: list[int] = []

    def save_run(self, clusters, metadata: ClusterRunMetadata) -> PersistedClusterRun:
        self.save_calls.append((tuple(clusters), metadata))
        return PersistedClusterRun(
            id=100,
            metadata=metadata,
            clusters=tuple(
                PersistedCluster(200 + cluster.cluster_id, 100, cluster.cluster_id)
                for cluster, _, _ in clusters
            ),
            created_at=CREATED_AT,
        )

    def find_latest_compatible_run(self, metadata, exclude_run_id=None):
        self.compatibility_calls.append((metadata, exclude_run_id))
        return self.previous_run

    def get_clusters_for_run(self, run_id: int) -> tuple[PersistedClusterDetails, ...]:
        self.cluster_run_ids.append(run_id)
        return self.previous_clusters

    def save_trends(self, run_id: int, trends, previous_run_id: int | None) -> None:
        self.trend_save_calls.append((run_id, tuple(trends)))

    def delete_run(self, run_id: int) -> None:
        self.deleted_run_ids.append(run_id)


class FakeMatchingService:
    def __init__(self, matches: list[ClusterMatch] | None = None) -> None:
        self.matches = matches or []
        self.calls: list[tuple] = []

    def match(self, previous_clusters, current_clusters) -> list[ClusterMatch]:
        self.calls.append((tuple(previous_clusters), tuple(current_clusters)))
        return self.matches


class FakeTrendService:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def detect(self, previous_clusters, current_clusters, matches) -> list[ClusterTrend]:
        self.calls.append((tuple(previous_clusters), tuple(current_clusters), tuple(matches)))
        return [
            ClusterTrend(
                current_cluster_id=match.current_cluster_id,
                previous_cluster_id=match.previous_cluster_id,
                label=next(
                    cluster.label
                    for cluster in current_clusters
                    if cluster.id == match.current_cluster_id
                ),
                current_count=next(
                    cluster.document_count
                    for cluster in current_clusters
                    if cluster.id == match.current_cluster_id
                ),
                previous_count=0,
                absolute_change=1,
                growth_rate=None,
                status="new" if match.previous_cluster_id is None else "stable",
                similarity=None if match.previous_cluster_id is None else match.similarity,
            )
            for match in matches
        ]


def _orchestrator(
    clustering_result: ClusteringResult,
    repository: FakeClusterRepository | None = None,
    labeling: FakeLabelingService | None = None,
    matching: FakeMatchingService | None = None,
    trend: FakeTrendService | None = None,
) -> tuple[
    AnalysisOrchestrator,
    FakeClusterRepository,
    FakeLabelingService,
    FakeMatchingService,
    FakeTrendService,
]:
    repository = repository or FakeClusterRepository()
    labeling = labeling or FakeLabelingService()
    matching = matching or FakeMatchingService()
    trend = trend or FakeTrendService()
    return (
        AnalysisOrchestrator(
            FakeClusteringService(clustering_result),
            labeling,
            repository,
            matching,
            trend,
            METADATA,
        ),
        repository,
        labeling,
        matching,
        trend,
    )


def test_first_run_persists_all_clusters_once_and_marks_them_new() -> None:
    result = ClusteringResult(2, (_cluster(3, _document(1, 0.2), _document(2, 0.4)),))
    orchestrator, repository, _, matching, trend = _orchestrator(result)

    analysis = orchestrator.run()

    assert analysis.run_id == 100
    assert analysis.created_at == CREATED_AT
    assert analysis.cluster_count == 1
    assert analysis.document_count == 2
    assert analysis.clusters[0].label.label == "label-3"
    assert analysis.matching == (ClusterMatch(203, None, 0.0, "new"),)
    assert analysis.trend[0].status == "new"
    assert repository.trend_save_calls == [(100, analysis.trend)]
    assert analysis.trend[0].current_cluster_id == 203
    assert len(repository.save_calls) == 1
    assert len(repository.save_calls[0][0]) == 1
    assert repository.compatibility_calls == [(METADATA, 100)]
    assert matching.calls == []
    assert len(trend.calls) == 1


def test_first_run_with_two_clusters_persists_two_new_trends_by_database_cluster_id() -> None:
    result = ClusteringResult(
        3,
        (
            _cluster(4, _document(1, 0.2), _document(2, 0.3)),
            _cluster(9, _document(3, 0.4)),
        ),
    )
    orchestrator, repository, _, _, _ = _orchestrator(result)

    analysis = orchestrator.run()

    assert [trend.current_cluster_id for trend in analysis.trend] == [204, 209]
    assert [trend.current_cluster_id for trend in analysis.trend] != [4, 9]
    assert all(trend.status == "new" for trend in analysis.trend)
    assert all(trend.previous_cluster_id is None for trend in analysis.trend)
    assert [trend.previous_count for trend in analysis.trend] == [0, 0]
    assert [trend.current_count for trend in analysis.trend] == [2, 1]
    assert all(trend.growth_rate is None for trend in analysis.trend)
    assert all(trend.similarity is None for trend in analysis.trend)
    assert repository.trend_save_calls == [(100, analysis.trend)]


def test_subsequent_run_matches_previous_clusters_and_detects_trends() -> None:
    previous_run = PersistedClusterRunDetails(99, CREATED_AT, METADATA)
    previous_cluster = PersistedClusterDetails(
        7, 99, 4, "previous", ("previous",), tuple([0.3] * 384), 2
    )
    matches = [ClusterMatch(201, 7, 0.95, "matched")]
    repository = FakeClusterRepository(previous_run, (previous_cluster,))
    matching = FakeMatchingService(matches)
    result = ClusteringResult(3, (_cluster(1, _document(1, 0.3), _document(2, 0.3)),))
    orchestrator, _, _, _, trend = _orchestrator(result, repository, matching=matching)

    analysis = orchestrator.run()

    assert analysis.matching == tuple(matches)
    assert analysis.trend[0].previous_cluster_id == 7
    assert repository.cluster_run_ids == [99]
    assert matching.calls[0][0][0].cluster_id == 7
    assert matching.calls[0][1][0].cluster_id == 201
    assert trend.calls[0][0][0].id == 7


def test_second_run_persists_one_matched_and_one_new_trend_for_current_clusters() -> None:
    previous_run = PersistedClusterRunDetails(99, CREATED_AT, METADATA)
    previous_cluster = PersistedClusterDetails(
        7, 99, 4, "previous", ("previous",), tuple([0.3] * 384), 2
    )
    repository = FakeClusterRepository(previous_run, (previous_cluster,))
    matching = FakeMatchingService([ClusterMatch(201, 7, 0.95, "matched"), ClusterMatch(202, None, 0.0, "new")])
    result = ClusteringResult(
        3,
        (
            _cluster(1, _document(1, 0.3), _document(2, 0.3)),
            _cluster(2, _document(3, 0.4)),
        ),
    )
    orchestrator, _, _, _, _ = _orchestrator(result, repository, matching=matching)

    analysis = orchestrator.run()

    assert [trend.current_cluster_id for trend in analysis.trend] == [201, 202]
    assert [(trend.previous_cluster_id, trend.status) for trend in analysis.trend] == [
        (7, "stable"),
        (None, "new"),
    ]
    assert repository.trend_save_calls == [(100, analysis.trend)]


def test_trend_persistence_failure_removes_the_incomplete_run() -> None:
    class FailingTrendRepository(FakeClusterRepository):
        def save_trends(self, run_id: int, trends, previous_run_id: int | None) -> None:
            raise RuntimeError("trend persistence failed")

    repository = FailingTrendRepository()
    orchestrator, _, _, _, _ = _orchestrator(
        ClusteringResult(1, (_cluster(1, _document(1, 0.2)),)), repository
    )

    with pytest.raises(RuntimeError, match="trend persistence failed"):
        orchestrator.run()

    assert repository.deleted_run_ids == [100]


@pytest.mark.parametrize("document_count", [0, 3])
def test_no_documents_or_all_noise_creates_one_empty_run(document_count: int) -> None:
    orchestrator, repository, labeling, matching, trend = _orchestrator(
        ClusteringResult(document_count, ())
    )

    analysis = orchestrator.run()

    assert analysis.cluster_count == 0
    assert analysis.document_count == document_count
    assert analysis.matching == ()
    assert analysis.trend == ()
    assert repository.save_calls == [((), METADATA)]
    assert labeling.cluster_ids == []
    assert matching.calls == []
    assert len(trend.calls) == 1


def test_labeling_error_does_not_persist_a_partial_run() -> None:
    result = ClusteringResult(2, (_cluster(1, _document(1, 0.2)), _cluster(2, _document(2, 0.3))))
    orchestrator, repository, labeling, _, _ = _orchestrator(
        result,
        labeling=FakeLabelingService(error_cluster_id=2),
    )

    with pytest.raises(ValueError, match="labeling failed"):
        orchestrator.run()

    assert labeling.cluster_ids == [1, 2]
    assert repository.save_calls == []


def test_rejects_embedding_model_mismatch_before_labeling_or_persistence() -> None:
    result = ClusteringResult(1, (_cluster(1, _document(1, 0.2, model="model-b")),))
    orchestrator, repository, labeling, _, _ = _orchestrator(result)

    with pytest.raises(ValueError, match="embedding_model does not match"):
        orchestrator.run()

    assert labeling.cluster_ids == []
    assert repository.save_calls == []


def test_cluster_order_is_deterministic() -> None:
    result = ClusteringResult(2, (_cluster(2, _document(2, 0.2)), _cluster(1, _document(1, 0.1))))
    orchestrator, repository, labeling, _, _ = _orchestrator(result)

    analysis = orchestrator.run()

    assert labeling.cluster_ids == [1, 2]
    assert [cluster.persisted_cluster.local_cluster_id for cluster in analysis.clusters] == [1, 2]
    assert [cluster[0].cluster_id for cluster in repository.save_calls[0][0]] == [1, 2]
