from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from app.clustering.schemas import ClusterCentroid, ClusterMatch, ClusterTrend, TrendCluster
from app.clustering.service import ClusteringResult, DocumentCluster
from app.clustering.topic_labeling import TopicLabel
from app.database.schemas import (
    ClusterRunMetadata,
    PersistedCluster,
    PersistedClusterDetails,
    PersistedClusterRun,
    PersistedClusterRunDetails,
)


class ClusteringRunner(Protocol):
    def cluster_documents_with_summary(self, embedding_model: str) -> ClusteringResult: ...


class ClusterLabeler(Protocol):
    def label_cluster(self, cluster: DocumentCluster) -> TopicLabel: ...


class ClusterMatcher(Protocol):
    def match(
        self,
        previous_clusters: Sequence[ClusterCentroid],
        current_clusters: Sequence[ClusterCentroid],
    ) -> list[ClusterMatch]: ...


class TrendDetector(Protocol):
    def detect(
        self,
        previous_clusters: Sequence[TrendCluster],
        current_clusters: Sequence[TrendCluster],
        matches: Sequence[ClusterMatch],
    ) -> list[ClusterTrend]: ...


class ClusterRunStore(Protocol):
    def save_run(
        self,
        clusters: Sequence[tuple[DocumentCluster, TopicLabel, Sequence[float] | None]],
        metadata: ClusterRunMetadata,
    ) -> PersistedClusterRun: ...

    def find_latest_compatible_run(
        self,
        metadata: ClusterRunMetadata,
        exclude_run_id: int | None = None,
    ) -> PersistedClusterRunDetails | None: ...

    def get_clusters_for_run(self, run_id: int) -> tuple[PersistedClusterDetails, ...]: ...

    def save_trends(
        self,
        run_id: int,
        trends: Sequence[ClusterTrend],
        previous_run_id: int | None,
    ) -> None: ...

    def delete_run(self, run_id: int) -> None: ...


@dataclass(frozen=True)
class AnalysisCluster:
    persisted_cluster: PersistedCluster
    label: TopicLabel
    centroid: tuple[float, ...]
    document_count: int


@dataclass(frozen=True)
class AnalysisRunResult:
    run_id: int
    created_at: datetime
    cluster_count: int
    document_count: int
    clusters: tuple[AnalysisCluster, ...]
    matching: tuple[ClusterMatch, ...]
    trend: tuple[ClusterTrend, ...]


class AnalysisOrchestrator:
    def __init__(
        self,
        clustering_service: ClusteringRunner,
        topic_labeling_service: ClusterLabeler,
        cluster_repository: ClusterRunStore,
        cluster_matching_service: ClusterMatcher,
        trend_detection_service: TrendDetector,
        metadata: ClusterRunMetadata,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._clustering_service = clustering_service
        self._topic_labeling_service = topic_labeling_service
        self._cluster_repository = cluster_repository
        self._cluster_matching_service = cluster_matching_service
        self._trend_detection_service = trend_detection_service
        self._metadata = metadata
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def run(self) -> AnalysisRunResult:
        clustering_result = self._clustering_service.cluster_documents_with_summary(
            self._metadata.embedding_model
        )
        self._validate_clustering_result(clustering_result)
        clusters = tuple(sorted(clustering_result.clusters, key=lambda cluster: cluster.cluster_id))
        self._validate_embedding_models(clusters)

        labeled_clusters = tuple(
            (cluster, self._topic_labeling_service.label_cluster(cluster), self._centroid(cluster))
            for cluster in clusters
        )
        self._validate_labels(labeled_clusters)

        persisted_run = self._cluster_repository.save_run(labeled_clusters, self._metadata)
        analysis_clusters = self._to_analysis_clusters(persisted_run, labeled_clusters)
        previous_run = self._cluster_repository.find_latest_compatible_run(
            self._metadata,
            exclude_run_id=persisted_run.id,
        )
        previous_clusters = ()
        if previous_run is not None:
            self._validate_previous_run(previous_run)
            previous_clusters = tuple(
                sorted(
                    self._cluster_repository.get_clusters_for_run(previous_run.id),
                    key=lambda cluster: cluster.id,
                )
            )

        current_centroids = tuple(
            ClusterCentroid(cluster_id=item.persisted_cluster.id, centroid=item.centroid)
            for item in analysis_clusters
        )
        if previous_run is None:
            matching = tuple(
                ClusterMatch(
                    current_cluster_id=cluster.cluster_id,
                    previous_cluster_id=None,
                    similarity=0.0,
                    status="new",
                )
                for cluster in sorted(current_centroids, key=lambda item: item.cluster_id)
            )
        else:
            matching = tuple(
                sorted(
                    self._cluster_matching_service.match(
                        tuple(
                            ClusterCentroid(cluster_id=cluster.id, centroid=cluster.centroid)
                            for cluster in previous_clusters
                        ),
                        current_centroids,
                    ),
                    key=lambda item: item.current_cluster_id,
                )
            )

        try:
            trend = tuple(
                sorted(
                    self._trend_detection_service.detect(
                        tuple(
                            TrendCluster(
                                id=cluster.id,
                                label=cluster.label,
                                document_count=cluster.document_count,
                            )
                            for cluster in previous_clusters
                        ),
                        tuple(
                            TrendCluster(
                                id=item.persisted_cluster.id,
                                label=item.label.label,
                                document_count=item.document_count,
                            )
                            for item in analysis_clusters
                        ),
                        matching,
                    ),
                    key=lambda item: item.current_cluster_id,
                )
            )
            self._cluster_repository.save_trends(
                persisted_run.id,
                trend,
                None if previous_run is None else previous_run.id,
            )
        except Exception:
            try:
                self._cluster_repository.delete_run(persisted_run.id)
            except Exception:
                pass
            raise
        return AnalysisRunResult(
            run_id=persisted_run.id,
            created_at=persisted_run.created_at or self._clock(),
            cluster_count=len(analysis_clusters),
            document_count=clustering_result.document_count,
            clusters=analysis_clusters,
            matching=matching,
            trend=trend,
        )

    def _validate_clustering_result(self, result: ClusteringResult) -> None:
        if isinstance(result.document_count, bool) or not isinstance(result.document_count, int):
            raise TypeError("document_count must be an integer")
        if result.document_count < 0:
            raise ValueError("document_count must be non-negative")
        cluster_ids = [cluster.cluster_id for cluster in result.clusters]
        if len(cluster_ids) != len(set(cluster_ids)):
            raise ValueError("cluster ids must be unique")

    def _validate_embedding_models(self, clusters: Sequence[DocumentCluster]) -> None:
        for cluster in clusters:
            if not cluster.documents:
                raise ValueError("cannot analyze an empty cluster")
            if any(
                document.embedding_model != self._metadata.embedding_model
                for document in cluster.documents
            ):
                raise ValueError("cluster document embedding_model does not match the analysis run")

    @staticmethod
    def _validate_labels(
        labeled_clusters: Sequence[tuple[DocumentCluster, TopicLabel, tuple[float, ...]]]
    ) -> None:
        if any(cluster.cluster_id != label.cluster_id for cluster, label, _ in labeled_clusters):
            raise ValueError("cluster and topic label ids must match")

    @staticmethod
    def _centroid(cluster: DocumentCluster) -> tuple[float, ...]:
        dimensions = zip(*(document.embedding for document in cluster.documents), strict=True)
        return tuple(sum(values) / len(cluster.documents) for values in dimensions)

    @staticmethod
    def _to_analysis_clusters(
        persisted_run: PersistedClusterRun,
        labeled_clusters: Sequence[tuple[DocumentCluster, TopicLabel, tuple[float, ...]]],
    ) -> tuple[AnalysisCluster, ...]:
        persisted_by_local_id = {
            cluster.local_cluster_id: cluster for cluster in persisted_run.clusters
        }
        local_cluster_ids = {cluster.cluster_id for cluster, _, _ in labeled_clusters}
        if set(persisted_by_local_id) != local_cluster_ids:
            raise ValueError("persisted clusters do not match the analyzed clusters")
        return tuple(
            AnalysisCluster(
                persisted_cluster=persisted_by_local_id[cluster.cluster_id],
                label=label,
                centroid=centroid,
                document_count=len(cluster.documents),
            )
            for cluster, label, centroid in labeled_clusters
        )

    def _validate_previous_run(self, previous_run: PersistedClusterRunDetails) -> None:
        if previous_run.metadata != self._metadata:
            raise ValueError("previous cluster run is not compatible with the analysis run")
