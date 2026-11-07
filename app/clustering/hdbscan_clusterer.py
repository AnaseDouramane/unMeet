from __future__ import annotations

from typing import Any, Protocol

import numpy as np


class DimensionalityReducer(Protocol):
    n_components: int

    def fit_transform(self, data: np.ndarray) -> np.ndarray: ...


class HDBSCANClusterer:
    """HDBSCAN with optional L2 normalisation and dimensionality reduction.

    Density-based clustering degrades on raw high-dimensional sentence embeddings: pairwise
    distances concentrate and almost everything becomes noise or tiny clusters. The production
    configuration (:meth:`for_text_embeddings`) therefore normalises vectors (so euclidean
    distance ranks like cosine similarity) and projects them with UMAP before HDBSCAN.
    """

    def __init__(
        self,
        min_cluster_size: int = 2,
        min_samples: int | None = None,
        metric: str = "euclidean",
        normalize: bool = False,
        reducer: DimensionalityReducer | None = None,
        reducer_name: str | None = None,
    ) -> None:
        self.min_cluster_size = min_cluster_size
        self.min_samples = min_samples
        self.metric = metric
        self.normalize = normalize
        self.reducer = reducer
        self.reducer_name = reducer_name

    @classmethod
    def for_text_embeddings(
        cls,
        min_cluster_size: int = 5,
        min_samples: int | None = 3,
        n_components: int = 10,
        n_neighbors: int = 15,
        random_state: int = 42,
    ) -> HDBSCANClusterer:
        """Recommended configuration for sentence-transformer embeddings."""
        return cls(
            min_cluster_size=min_cluster_size,
            min_samples=min_samples,
            metric="euclidean",
            normalize=True,
            reducer=_LazyUMAP(
                n_components=n_components,
                n_neighbors=n_neighbors,
                random_state=random_state,
            ),
            reducer_name=f"umap{n_components}n{n_neighbors}",
        )

    @property
    def run_metric(self) -> str:
        """Metric signature persisted with a cluster run.

        Runs are only compared for trends when their signatures match, so the preprocessing
        steps are part of the signature.
        """
        parts = []
        if self.normalize:
            parts.append("l2")
        if self.reducer is not None:
            parts.append(self.reducer_name or type(self.reducer).__name__.lower())
        parts.append(self.metric)
        return "+".join(parts)

    def fit_predict(self, embeddings: Any) -> tuple[Any, np.ndarray]:
        if not self.can_cluster(len(embeddings)):
            return None, np.full(len(embeddings), -1, dtype=int)

        import hdbscan

        features = self._prepare_features(embeddings)
        model = hdbscan.HDBSCAN(
            min_cluster_size=self.min_cluster_size,
            min_samples=self.min_samples,
            metric=self.metric,
            prediction_data=True,
        )
        labels = model.fit_predict(features)
        return model, labels

    def can_cluster(self, document_count: int) -> bool:
        effective_min_samples = (
            self.min_cluster_size if self.min_samples is None else self.min_samples
        )
        return document_count >= max(self.min_cluster_size, effective_min_samples)

    def _prepare_features(self, embeddings: Any) -> Any:
        if not self.normalize and self.reducer is None:
            return embeddings

        features = np.asarray(embeddings, dtype=float)
        if self.normalize:
            norms = np.linalg.norm(features, axis=1, keepdims=True)
            features = features / np.where(norms == 0, 1.0, norms)
        # UMAP needs more points than output dimensions; tiny corpora skip the projection.
        if self.reducer is not None and len(features) > self.reducer.n_components + 1:
            features = self.reducer.fit_transform(features)
        return features


class _LazyUMAP:
    """Imports umap only when clustering actually runs (the import is slow)."""

    def __init__(self, n_components: int, n_neighbors: int, random_state: int) -> None:
        self.n_components = n_components
        self.n_neighbors = n_neighbors
        self.random_state = random_state

    def fit_transform(self, data: np.ndarray) -> np.ndarray:
        import umap

        reducer = umap.UMAP(
            n_components=self.n_components,
            n_neighbors=min(self.n_neighbors, len(data) - 1),
            min_dist=0.0,
            metric="euclidean",
            random_state=self.random_state,
        )
        return np.asarray(reducer.fit_transform(data))
