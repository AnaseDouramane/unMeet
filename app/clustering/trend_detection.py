from __future__ import annotations

import math
from collections.abc import Sequence
from numbers import Real
from typing import Literal

from app.clustering.schemas import ClusterMatch, ClusterTrend, TrendCluster


class TrendDetectionService:
    _SIMILARITY_TOLERANCE = 1e-12

    def __init__(self, change_threshold: float = 0.2) -> None:
        self.change_threshold = self._normalize_threshold(change_threshold)

    def detect(
        self,
        previous_clusters: Sequence[TrendCluster],
        current_clusters: Sequence[TrendCluster],
        matches: Sequence[ClusterMatch],
    ) -> list[ClusterTrend]:
        previous_by_id = self._index_clusters(previous_clusters, "previous")
        current_by_id = self._index_clusters(current_clusters, "current")
        matches_by_current_id = self._index_matches(
            matches,
            previous_by_id,
            current_by_id,
        )

        if set(matches_by_current_id) != set(current_by_id):
            raise ValueError("matching results must cover every current cluster")

        return [
            self._to_trend(
                current_by_id[current_cluster_id],
                matches_by_current_id[current_cluster_id],
                previous_by_id,
            )
            for current_cluster_id in sorted(current_by_id)
        ]

    def _to_trend(
        self,
        current_cluster: TrendCluster,
        match: ClusterMatch,
        previous_by_id: dict[int, TrendCluster],
    ) -> ClusterTrend:
        if match.previous_cluster_id is None:
            return ClusterTrend(
                current_cluster_id=current_cluster.id,
                previous_cluster_id=None,
                label=current_cluster.label,
                current_count=current_cluster.document_count,
                previous_count=0,
                absolute_change=current_cluster.document_count,
                growth_rate=None,
                status="new",
                similarity=None,
            )

        previous_cluster = previous_by_id[match.previous_cluster_id]
        previous_count = previous_cluster.document_count
        current_count = current_cluster.document_count
        absolute_change = current_count - previous_count
        growth_rate = None if previous_count == 0 else absolute_change / previous_count

        return ClusterTrend(
            current_cluster_id=current_cluster.id,
            previous_cluster_id=previous_cluster.id,
            label=current_cluster.label,
            current_count=current_count,
            previous_count=previous_count,
            absolute_change=absolute_change,
            growth_rate=growth_rate,
            status=self._status_for_change(absolute_change, growth_rate),
            similarity=match.similarity,
        )

    def _status_for_change(
        self,
        absolute_change: int,
        growth_rate: float | None,
    ) -> Literal["rising", "stable", "falling"]:
        if growth_rate is None:
            return "rising" if absolute_change > 0 else "stable"
        if growth_rate > self.change_threshold:
            return "rising"
        if growth_rate < -self.change_threshold:
            return "falling"
        return "stable"

    @staticmethod
    def _index_clusters(
        clusters: Sequence[TrendCluster],
        description: str,
    ) -> dict[int, TrendCluster]:
        clusters_by_id: dict[int, TrendCluster] = {}
        for cluster in clusters:
            if isinstance(cluster.document_count, bool) or not isinstance(
                cluster.document_count, int
            ):
                raise ValueError(f"{description} cluster document_count must be an integer")
            if cluster.document_count < 0:
                raise ValueError(f"{description} cluster document_count must be non-negative")
            if cluster.id in clusters_by_id:
                raise ValueError(f"duplicate {description} cluster id: {cluster.id}")
            clusters_by_id[cluster.id] = cluster
        return clusters_by_id

    @staticmethod
    def _index_matches(
        matches: Sequence[ClusterMatch],
        previous_by_id: dict[int, TrendCluster],
        current_by_id: dict[int, TrendCluster],
    ) -> dict[int, ClusterMatch]:
        matches_by_current_id: dict[int, ClusterMatch] = {}
        matched_previous_ids: set[int] = set()
        for match in matches:
            if match.current_cluster_id not in current_by_id:
                raise ValueError("matching result references an unknown current cluster")
            if match.current_cluster_id in matches_by_current_id:
                raise ValueError("duplicate current_cluster_id in matching results")
            if match.similarity is None:
                if match.previous_cluster_id is not None:
                    raise ValueError("matched clusters must include a similarity")
            else:
                TrendDetectionService._validate_similarity(match.similarity)

            if match.previous_cluster_id is None:
                if match.status != "new":
                    raise ValueError("unmatched clusters must have status 'new'")
            else:
                if match.previous_cluster_id not in previous_by_id:
                    raise ValueError("matching result references an unknown previous cluster")
                if match.status != "matched":
                    raise ValueError("matched clusters must have status 'matched'")
                if match.previous_cluster_id in matched_previous_ids:
                    raise ValueError("previous clusters may only be matched once")
                matched_previous_ids.add(match.previous_cluster_id)

            matches_by_current_id[match.current_cluster_id] = match
        return matches_by_current_id

    @classmethod
    def _validate_similarity(cls, similarity: float) -> None:
        if isinstance(similarity, bool) or not isinstance(similarity, Real):
            raise ValueError("matching similarity must be numeric")
        normalized_similarity = float(similarity)
        if not math.isfinite(normalized_similarity):
            raise ValueError("matching similarity must be finite")
        if not (
            -1.0 - cls._SIMILARITY_TOLERANCE
            <= normalized_similarity
            <= 1.0 + cls._SIMILARITY_TOLERANCE
        ):
            raise ValueError("matching similarity must be between -1 and 1")

    @staticmethod
    def _normalize_threshold(change_threshold: float) -> float:
        if isinstance(change_threshold, bool) or not isinstance(change_threshold, Real):
            raise TypeError("change_threshold must be a number")
        normalized_threshold = float(change_threshold)
        if not math.isfinite(normalized_threshold):
            raise ValueError("change_threshold must be finite")
        if normalized_threshold < 0:
            raise ValueError("change_threshold must be non-negative")
        return normalized_threshold
