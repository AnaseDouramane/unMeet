import numpy as np


class HDBSCANClusterer:
    def __init__(
        self,
        min_cluster_size: int = 5,
        min_samples: int | None = None,
        metric: str = "euclidean",
    ) -> None:
        self.min_cluster_size = min_cluster_size
        self.min_samples = min_samples
        self.metric = metric

    def fit_predict(self, embeddings):
        if not self.can_cluster(len(embeddings)):
            return None, np.full(len(embeddings), -1, dtype=int)

        import hdbscan

        model = hdbscan.HDBSCAN(
            min_cluster_size=self.min_cluster_size,
            min_samples=self.min_samples,
            metric=self.metric,
            prediction_data=True,
        )
        labels = model.fit_predict(embeddings)
        return model, labels

    def can_cluster(self, document_count: int) -> bool:
        effective_min_samples = (
            self.min_cluster_size if self.min_samples is None else self.min_samples
        )
        return document_count >= max(self.min_cluster_size, effective_min_samples)
