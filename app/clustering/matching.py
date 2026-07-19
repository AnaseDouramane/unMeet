from __future__ import annotations

from collections.abc import Sequence
from numbers import Real

import numpy as np

from app.clustering.schemas import ClusterCentroid, ClusterMatch


class ClusterMatchingService:
    def __init__(self, similarity_threshold: float = 0.8) -> None:
        self.similarity_threshold = self._normalize_threshold(similarity_threshold)

    def match(
        self,
        previous_clusters: Sequence[ClusterCentroid],
        current_clusters: Sequence[ClusterCentroid],
    ) -> list[ClusterMatch]:
        normalized_previous = sorted(
            (self._normalize_cluster(cluster) for cluster in previous_clusters),
            key=lambda cluster: cluster[0],
        )
        normalized_current = sorted(
            (self._normalize_cluster(cluster) for cluster in current_clusters),
            key=lambda cluster: cluster[0],
        )
        candidates = [
            (similarity, current_cluster_id, previous_cluster_id)
            for current_cluster_id, current_centroid in normalized_current
            for previous_cluster_id, previous_centroid in normalized_previous
            if (similarity := float(np.dot(current_centroid, previous_centroid)))
            >= self.similarity_threshold
        ]
        candidates.sort(key=lambda candidate: (-candidate[0], candidate[1], candidate[2]))

        matched_current_ids: set[int] = set()
        matched_previous_ids: set[int] = set()
        matches_by_current_id: dict[int, tuple[int, float]] = {}
        for similarity, current_cluster_id, previous_cluster_id in candidates:
            if (
                current_cluster_id in matched_current_ids
                or previous_cluster_id in matched_previous_ids
            ):
                continue
            matched_current_ids.add(current_cluster_id)
            matched_previous_ids.add(previous_cluster_id)
            matches_by_current_id[current_cluster_id] = (previous_cluster_id, similarity)

        return [
            self._to_match(current_cluster_id, matches_by_current_id.get(current_cluster_id))
            for current_cluster_id, _ in normalized_current
        ]

    @staticmethod
    def _to_match(
        current_cluster_id: int,
        match: tuple[int, float] | None,
    ) -> ClusterMatch:
        if match is None:
            return ClusterMatch(
                current_cluster_id=current_cluster_id,
                previous_cluster_id=None,
                similarity=0.0,
                status="new",
            )
        previous_cluster_id, similarity = match
        return ClusterMatch(
            current_cluster_id=current_cluster_id,
            previous_cluster_id=previous_cluster_id,
            similarity=similarity,
            status="matched",
        )

    @staticmethod
    def _normalize_cluster(cluster: ClusterCentroid) -> tuple[int, np.ndarray]:
        centroid = cluster.centroid
        try:
            centroid_length = len(centroid)
        except TypeError as error:
            raise ValueError("centroid must be a one-dimensional sequence") from error
        if centroid_length != 384:
            raise ValueError("centroid must contain exactly 384 values")
        if any(isinstance(value, bool) or not isinstance(value, Real) for value in centroid):
            raise ValueError("centroid values must be numeric")

        numeric_centroid = np.asarray(centroid, dtype=float)
        if numeric_centroid.ndim != 1:
            raise ValueError("centroid must be a one-dimensional sequence")
        if not np.isfinite(numeric_centroid).all():
            raise ValueError("centroid values must be finite")

        norm = float(np.linalg.norm(numeric_centroid))
        if norm == 0.0:
            raise ValueError("centroid must not be the zero vector")
        return cluster.cluster_id, numeric_centroid / norm

    @staticmethod
    def _normalize_threshold(similarity_threshold: float) -> float:
        if isinstance(similarity_threshold, bool) or not isinstance(similarity_threshold, Real):
            raise TypeError("similarity_threshold must be a number")
        normalized_threshold = float(similarity_threshold)
        if not np.isfinite(normalized_threshold):
            raise ValueError("similarity_threshold must be finite")
        if not -1.0 <= normalized_threshold <= 1.0:
            raise ValueError("similarity_threshold must be between -1 and 1")
        return normalized_threshold
