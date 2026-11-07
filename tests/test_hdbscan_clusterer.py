import sys
from types import SimpleNamespace

import numpy as np
import pytest

from app.clustering.hdbscan_clusterer import HDBSCANClusterer


class FakeHDBSCAN:
    instances: list["FakeHDBSCAN"] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.embeddings = None
        self.__class__.instances.append(self)

    def fit_predict(self, embeddings):
        self.embeddings = embeddings
        return np.zeros(len(embeddings), dtype=int)


@pytest.fixture(autouse=True)
def reset_fake_hdbscan() -> None:
    FakeHDBSCAN.instances = []


@pytest.mark.parametrize(
    ("document_count", "min_cluster_size", "min_samples"),
    [
        (0, 5, None),
        (1, 5, None),
        (2, 2, 3),
        (3, 4, 2),
    ],
)
def test_fit_predict_returns_only_noise_when_documents_are_insufficient(
    monkeypatch, document_count: int, min_cluster_size: int, min_samples: int | None
) -> None:
    monkeypatch.setitem(sys.modules, "hdbscan", SimpleNamespace(HDBSCAN=FakeHDBSCAN))
    embeddings = np.zeros((document_count, 384))

    model, labels = HDBSCANClusterer(min_cluster_size, min_samples).fit_predict(embeddings)

    assert model is None
    assert labels.tolist() == [-1] * document_count
    assert FakeHDBSCAN.instances == []


def test_fit_predict_calls_hdbscan_when_documents_are_sufficient(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "hdbscan", SimpleNamespace(HDBSCAN=FakeHDBSCAN))
    embeddings = np.zeros((4, 384))

    model, labels = HDBSCANClusterer(
        min_cluster_size=4, min_samples=2, metric="manhattan"
    ).fit_predict(embeddings)

    assert model is FakeHDBSCAN.instances[0]
    assert labels.tolist() == [0, 0, 0, 0]
    assert model.embeddings is embeddings
    assert model.kwargs == {
        "min_cluster_size": 4,
        "min_samples": 2,
        "metric": "manhattan",
        "prediction_data": True,
    }


class RecordingReducer:
    n_components = 2

    def __init__(self) -> None:
        self.inputs: list[np.ndarray] = []

    def fit_transform(self, data: np.ndarray) -> np.ndarray:
        self.inputs.append(data)
        return data[:, : self.n_components]


def test_normalisation_scales_vectors_to_unit_length(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "hdbscan", SimpleNamespace(HDBSCAN=FakeHDBSCAN))
    embeddings = np.array([[3.0, 4.0], [0.0, 2.0], [0.0, 0.0]])

    HDBSCANClusterer(min_cluster_size=2, normalize=True).fit_predict(embeddings)

    features = FakeHDBSCAN.instances[0].embeddings
    assert np.allclose(features, [[0.6, 0.8], [0.0, 1.0], [0.0, 0.0]])


def test_reducer_output_is_clustered_when_corpus_is_large_enough(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "hdbscan", SimpleNamespace(HDBSCAN=FakeHDBSCAN))
    reducer = RecordingReducer()
    embeddings = np.arange(20, dtype=float).reshape(5, 4)

    HDBSCANClusterer(min_cluster_size=2, reducer=reducer).fit_predict(embeddings)

    assert len(reducer.inputs) == 1
    assert FakeHDBSCAN.instances[0].embeddings.shape == (5, 2)


def test_reducer_is_skipped_for_tiny_corpora(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "hdbscan", SimpleNamespace(HDBSCAN=FakeHDBSCAN))
    reducer = RecordingReducer()

    HDBSCANClusterer(min_cluster_size=2, reducer=reducer).fit_predict(np.ones((3, 4)))

    assert reducer.inputs == []


def test_run_metric_signature_describes_preprocessing() -> None:
    assert HDBSCANClusterer().run_metric == "euclidean"
    assert HDBSCANClusterer.for_text_embeddings().run_metric == "l2+umap10n15+euclidean"
    assert len(HDBSCANClusterer.for_text_embeddings().run_metric) <= 50


def _topic_corpus(seed: int = 7) -> tuple[np.ndarray, np.ndarray]:
    """Three topics on the unit sphere in 384 dimensions, with realistic per-document noise."""
    rng = np.random.default_rng(seed)
    centres = rng.normal(size=(3, 384))
    vectors, labels = [], []
    for topic, centre in enumerate(centres):
        centre = centre / np.linalg.norm(centre)
        for _ in range(40):
            noise = rng.normal(scale=0.06, size=384)
            vectors.append(centre + noise)
            labels.append(topic)
    return np.asarray(vectors), np.asarray(labels)


def test_text_embedding_configuration_recovers_topics_on_real_backends() -> None:
    pytest.importorskip("umap")
    pytest.importorskip("hdbscan")
    from sklearn.metrics import adjusted_rand_score

    embeddings, truth = _topic_corpus()

    _, labels = HDBSCANClusterer.for_text_embeddings().fit_predict(embeddings)

    clustered = labels != -1
    assert clustered.mean() >= 0.9
    assert adjusted_rand_score(truth[clustered], labels[clustered]) >= 0.95
