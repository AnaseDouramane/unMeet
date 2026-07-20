from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from typing import TYPE_CHECKING

import numpy as np

from app.clustering.hdbscan_clusterer import HDBSCANClusterer
from app.clustering.schemas import ClusterableDocument

if TYPE_CHECKING:
    from app.database.repository import SourceItemRepository


@dataclass(frozen=True)
class DocumentCluster:
    cluster_id: int
    documents: tuple[ClusterableDocument, ...]


@dataclass(frozen=True)
class ClusteringResult:
    document_count: int
    clusters: tuple[DocumentCluster, ...]


class ClusteringService:
    def __init__(
        self, repository: SourceItemRepository, clusterer: HDBSCANClusterer | None = None
    ) -> None:
        self._repository = repository
        self._clusterer = clusterer or HDBSCANClusterer()

    def cluster_documents(self, embedding_model: str) -> list[DocumentCluster]:
        return list(self.cluster_documents_with_summary(embedding_model).clusters)

    def cluster_documents_with_summary(self, embedding_model: str) -> ClusteringResult:
        documents = self._repository.find_all_with_embeddings(embedding_model)
        if not documents:
            return ClusteringResult(document_count=0, clusters=())

        embeddings = self._validate_embeddings(documents)
        _, labels = self._clusterer.fit_predict(embeddings)

        clusters: dict[int, list[ClusterableDocument]] = {}
        for document, label in zip(documents, labels, strict=True):
            cluster_id = int(label)
            if cluster_id == -1:
                continue
            clusters.setdefault(cluster_id, []).append(document)

        return ClusteringResult(
            document_count=len(documents),
            clusters=tuple(
                DocumentCluster(cluster_id=cluster_id, documents=tuple(cluster_documents))
                for cluster_id, cluster_documents in sorted(clusters.items())
            ),
        )

    @staticmethod
    def _validate_embeddings(documents: list[ClusterableDocument]) -> np.ndarray:
        embeddings = [document.embedding for document in documents]
        if len(embeddings) != len(documents):
            raise ValueError("the number of embeddings must match the number of documents")

        for index, embedding in enumerate(embeddings):
            try:
                embedding_length = len(embedding)
            except TypeError as error:
                raise ValueError(
                    f"embedding at index {index} must be a one-dimensional sequence"
                ) from error
            if embedding_length != 384:
                raise ValueError(f"embedding at index {index} must contain exactly 384 values")
            if any(isinstance(value, bool) or not isinstance(value, Real) for value in embedding):
                raise ValueError(f"embedding at index {index} contains non-numeric values")

        matrix = np.asarray(embeddings, dtype=object)
        if matrix.ndim != 2:
            raise ValueError("embedding matrix must be two-dimensional")
        if matrix.shape[0] != len(documents):
            raise ValueError("the number of embeddings must match the number of documents")
        if matrix.shape[1] != 384:
            raise ValueError("each embedding must contain exactly 384 values")

        try:
            numeric_matrix = np.asarray(embeddings, dtype=float)
        except (TypeError, ValueError) as error:
            raise ValueError("embedding values must be numeric") from error

        if not np.isfinite(numeric_matrix).all():
            raise ValueError("embedding values must be finite")

        return numeric_matrix
