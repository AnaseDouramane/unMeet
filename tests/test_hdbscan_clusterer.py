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
