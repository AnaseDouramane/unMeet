import inspect

import pytest

from app.clustering.schemas import ClusterableDocument
from app.clustering.service import DocumentCluster
from app.clustering.topic_labeling import TopicLabelingService


def _document(document_id: int, document_text: str) -> ClusterableDocument:
    return ClusterableDocument(
        id=document_id,
        source="hackernews",
        external_id=str(document_id),
        document_text=document_text,
        embedding=tuple([0.1] * 384),
    )


def _cluster(*documents: ClusterableDocument, cluster_id: int = 7) -> DocumentCluster:
    return DocumentCluster(cluster_id=cluster_id, documents=documents)


def test_topic_labeling_has_no_source_item_model_dependency() -> None:
    assert "SourceItemModel" not in inspect.getsource(TopicLabelingService)


def test_topic_labeling_returns_deterministic_keywords_and_label() -> None:
    cluster = _cluster(
        _document(1, "cloud deployment automation"),
        _document(2, "cloud security automation"),
    )

    result = TopicLabelingService(max_keywords=3).label_cluster(cluster)

    assert result.cluster_id == 7
    assert result.keywords == ("automation", "cloud", "deployment")
    assert result.label == "automation, cloud, deployment"


def test_topic_labeling_ignores_english_stopwords() -> None:
    cluster = _cluster(
        _document(1, "the cloud and the cloud"),
        _document(2, "tools for cloud"),
    )

    result = TopicLabelingService(max_keywords=5).label_cluster(cluster)

    assert "the" not in result.keywords
    assert "and" not in result.keywords
    assert "for" not in result.keywords
    assert "cloud" in result.keywords


def test_topic_labeling_respects_max_keywords() -> None:
    result = TopicLabelingService(max_keywords=2).label_cluster(
        _cluster(_document(1, "alpha beta gamma delta"))
    )

    assert len(result.keywords) == 2
    assert result.label == ", ".join(result.keywords)


def test_topic_labeling_rejects_empty_cluster() -> None:
    with pytest.raises(ValueError, match="empty cluster"):
        TopicLabelingService().label_cluster(_cluster())


def test_topic_labeling_rejects_empty_text() -> None:
    with pytest.raises(ValueError, match="empty text"):
        TopicLabelingService().label_cluster(_cluster(_document(1, "")))


def test_topic_labeling_rejects_stopword_only_text() -> None:
    with pytest.raises(ValueError, match="stopword-only"):
        TopicLabelingService().label_cluster(_cluster(_document(1, "with the for")))
