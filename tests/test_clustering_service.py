import inspect

import numpy as np
import pytest

from app.clustering.schemas import ClusterableDocument
from app.clustering.service import ClusteringService, DocumentCluster


class FakeRepository:
    def __init__(self, documents: list[ClusterableDocument]) -> None:
        self.documents = documents
        self.calls = 0

    def find_all_with_embeddings(self) -> list[ClusterableDocument]:
        self.calls += 1
        return self.documents


class FakeClusterer:
    def __init__(self, labels: list[int]) -> None:
        self.labels = labels
        self.received_embeddings = None

    def fit_predict(self, embeddings):
        self.received_embeddings = embeddings
        return object(), self.labels


def _document(document_id: int, value: float) -> ClusterableDocument:
    return ClusterableDocument(
        id=document_id,
        source="hackernews",
        external_id=str(document_id),
        document_text="cloud automation",
        embedding=tuple([value] * 384),
    )


def test_clustering_has_no_source_item_model_dependency() -> None:
    assert "SourceItemModel" not in inspect.getsource(ClusteringService)
    assert "SourceItemModel" not in inspect.getsource(DocumentCluster)


def test_cluster_documents_reads_embeddings_and_returns_groups_in_memory() -> None:
    documents = [_document(1, 0.1), _document(2, 0.2), _document(3, 0.3)]
    repository = FakeRepository(documents)
    clusterer = FakeClusterer([1, 0, 1])

    clusters = ClusteringService(repository, clusterer).cluster_documents()

    assert repository.calls == 1
    assert clusterer.received_embeddings.shape == (3, 384)
    assert [(cluster.cluster_id, [document.id for document in cluster.documents]) for cluster in clusters] == [
        (0, [2]),
        (1, [1, 3]),
    ]


def test_cluster_documents_ignores_hdbscan_noise() -> None:
    documents = [_document(1, 0.1), _document(2, 0.2)]
    clusterer = FakeClusterer([-1, 2])

    clusters = ClusteringService(FakeRepository(documents), clusterer).cluster_documents()

    assert len(clusters) == 1
    assert clusters[0].cluster_id == 2
    assert [document.id for document in clusters[0].documents] == [2]


def test_cluster_documents_returns_empty_result_without_embeddings() -> None:
    repository = FakeRepository([])

    assert ClusteringService(repository, FakeClusterer([])).cluster_documents() == []
    assert repository.calls == 1


@pytest.mark.parametrize(
    ("embedding_length", "message"),
    [(383, "exactly 384"), (385, "exactly 384")],
)
def test_cluster_documents_rejects_embedding_with_invalid_length(
    embedding_length: int, message: str
) -> None:
    document = _document(1, 0.1)
    object.__setattr__(document, "embedding", tuple([0.1] * embedding_length))
    clusterer = FakeClusterer([0])

    with pytest.raises(ValueError, match=message):
        ClusteringService(FakeRepository([document]), clusterer).cluster_documents()

    assert clusterer.received_embeddings is None


@pytest.mark.parametrize("invalid_value", [np.nan, np.inf, -np.inf])
def test_cluster_documents_rejects_non_finite_embedding_values(invalid_value: float) -> None:
    document = _document(1, 0.1)
    embedding = list(document.embedding)
    embedding[10] = invalid_value
    object.__setattr__(document, "embedding", tuple(embedding))
    clusterer = FakeClusterer([0])

    with pytest.raises(ValueError, match="finite"):
        ClusteringService(FakeRepository([document]), clusterer).cluster_documents()

    assert clusterer.received_embeddings is None


def test_cluster_documents_rejects_incoherent_embedding_shape() -> None:
    document = _document(1, 0.1)
    object.__setattr__(document, "embedding", 0.1)
    clusterer = FakeClusterer([0])

    with pytest.raises(ValueError, match="one-dimensional sequence"):
        ClusteringService(FakeRepository([document]), clusterer).cluster_documents()

    assert clusterer.received_embeddings is None
