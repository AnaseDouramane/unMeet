"""Readable problem statements for clusters, written by an LLM.

TF-IDF keywords ("invoice, csv, export") are still computed and stored; the LLM turns the most
representative documents into a one-line problem statement a customer can act on
("Finance teams re-key invoice data from CSV exports by hand"). Any provider failure falls
back to the keyword label so a run never fails because of labeling.
"""

from __future__ import annotations

import logging

import numpy as np

from app.clustering.service import DocumentCluster
from app.clustering.topic_labeling import TopicLabel, TopicLabelingService
from app.llm.client import ChatCompletionsClient, LLMRequestError, LLMResponseError

logger = logging.getLogger(__name__)

LABEL_PROMPT = """You name clusters of public posts in which people describe problems.
Write the shared problem as one plain-English sentence of at most 12 words, from the point of
view of the people who have it (who + what goes wrong). No marketing language, no product
names unless every post is about that product, no trailing period. Answer with the sentence
only."""

MAX_LABEL_LENGTH = 120


class LLMTopicLabelingService:
    def __init__(
        self,
        client: ChatCompletionsClient,
        keyword_labeler: TopicLabelingService | None = None,
        representative_documents: int = 8,
        max_document_chars: int = 600,
    ) -> None:
        if representative_documents <= 0:
            raise ValueError("representative_documents must be positive")
        if max_document_chars <= 0:
            raise ValueError("max_document_chars must be positive")
        self._client = client
        self._keyword_labeler = keyword_labeler or TopicLabelingService()
        self.representative_documents = representative_documents
        self.max_document_chars = max_document_chars

    def label_cluster(self, cluster: DocumentCluster) -> TopicLabel:
        keyword_label = self._keyword_labeler.label_cluster(cluster)
        excerpts = [
            document.document_text.strip()[: self.max_document_chars]
            for document in self._representatives(cluster)
        ]
        prompt = "\n\n".join(f"Post {index}:\n{text}" for index, text in enumerate(excerpts, 1))
        try:
            answer = self._client.complete(
                messages=[
                    {"role": "system", "content": LABEL_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
            )
        except (LLMRequestError, LLMResponseError) as error:
            logger.warning("LLM labeling failed for cluster %s: %s", cluster.cluster_id, error)
            return keyword_label

        label = _clean_label(answer)
        if label is None:
            return keyword_label
        return TopicLabel(
            cluster_id=cluster.cluster_id, label=label, keywords=keyword_label.keywords
        )

    def _representatives(self, cluster: DocumentCluster):
        """Documents closest to the cluster centroid represent it best."""
        embeddings = np.asarray([document.embedding for document in cluster.documents], float)
        centroid = embeddings.mean(axis=0)
        distances = np.linalg.norm(embeddings - centroid, axis=1)
        order = np.argsort(distances, kind="stable")[: self.representative_documents]
        return [cluster.documents[int(index)] for index in order]


def _clean_label(answer: str) -> str | None:
    lines = [line.strip() for line in answer.strip().splitlines() if line.strip()]
    if not lines:
        return None
    label = lines[0].strip().strip("\"'“”*").rstrip(".").strip()
    if not label:
        return None
    return label[:MAX_LABEL_LENGTH]
