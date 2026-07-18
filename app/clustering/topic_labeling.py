from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from app.clustering.service import DocumentCluster


@dataclass(frozen=True)
class TopicLabel:
    cluster_id: int
    label: str
    keywords: tuple[str, ...]


class TopicLabelingService:
    def __init__(self, max_keywords: int = 5) -> None:
        if isinstance(max_keywords, bool) or not isinstance(max_keywords, int):
            raise TypeError("max_keywords must be an integer")
        if max_keywords <= 0:
            raise ValueError("max_keywords must be positive")
        self.max_keywords = max_keywords

    def label_cluster(self, cluster: DocumentCluster) -> TopicLabel:
        if not cluster.documents:
            raise ValueError("cannot label an empty cluster")

        texts = [self._document_text(document) for document in cluster.documents]
        if any(not text for text in texts):
            raise ValueError("cannot label a cluster containing empty text")

        vectorizer = TfidfVectorizer(stop_words="english")
        try:
            matrix = vectorizer.fit_transform(texts)
        except ValueError as error:
            raise ValueError("cannot extract keywords from empty or stopword-only text") from error

        scores = np.asarray(matrix.mean(axis=0)).ravel()
        terms = vectorizer.get_feature_names_out()
        ranked_terms = sorted(
            zip(terms, scores, strict=True),
            key=lambda item: (-float(item[1]), item[0]),
        )
        keywords = tuple(term for term, _ in ranked_terms[: self.max_keywords])
        if not keywords:
            raise ValueError("cannot extract keywords from the cluster")

        return TopicLabel(
            cluster_id=cluster.cluster_id,
            label=", ".join(keywords),
            keywords=keywords,
        )

    @staticmethod
    def _document_text(document: object) -> str:
        return (getattr(document, "document_text", None) or "").strip()