import pytest

from app.clustering.service import DocumentCluster
from app.clustering.topic_labeling import TopicLabelingService
from app.database.models import SourceItemModel


def _document(title: str, document_text: str) -> SourceItemModel:
    document = SourceItemModel()
    document.title = title
    document.document_text = document_text
    return document


def _cluster(*documents: SourceItemModel, cluster_id: int = 7) -> DocumentCluster:
    return DocumentCluster(cluster_id=cluster_id, documents=documents)


def test_topic_labeling_returns_deterministic_keywords_and_label() -> None:
    cluster = _cluster(
        _document("Cloud deployment", "cloud deployment automation"),
        _document("Cloud security", "cloud security automation"),
    )

    result = TopicLabelingService(max_keywords=3).label_cluster(cluster)

    assert result.cluster_id == 7
    assert result.keywords == ("automation", "cloud", "deployment")
    assert result.label == "automation, cloud, deployment"


def test_topic_labeling_ignores_english_stopwords() -> None:
    cluster = _cluster(
        _document("The cloud", "the cloud and the cloud"),
        _document("Cloud tools", "tools for cloud"),
    )

    result = TopicLabelingService(max_keywords=5).label_cluster(cluster)

    assert "the" not in result.keywords
    assert "and" not in result.keywords
    assert "for" not in result.keywords
    assert "cloud" in result.keywords


def test_topic_labeling_respects_max_keywords() -> None:
    cluster = _cluster(_document("Alpha beta gamma", "alpha beta gamma delta"))

    result = TopicLabelingService(max_keywords=2).label_cluster(cluster)

    assert len(result.keywords) == 2
    assert result.label == ", ".join(result.keywords)


def test_topic_labeling_rejects_empty_cluster() -> None:
    with pytest.raises(ValueError, match="empty cluster"):
        TopicLabelingService().label_cluster(_cluster())


def test_topic_labeling_rejects_empty_text() -> None:
    cluster = _cluster(_document("", ""))

    with pytest.raises(ValueError, match="empty text"):
        TopicLabelingService().label_cluster(cluster)


def test_topic_labeling_rejects_stopword_only_text() -> None:
    cluster = _cluster(_document("the and", "with the for"))

    with pytest.raises(ValueError, match="stopword-only"):
        TopicLabelingService().label_cluster(cluster)
def test_topic_labeling_uses_only_document_text() -> None:
    cluster = _cluster(
        _document("<b>Security</b> security security", "cloud deployment"),
        _document("HTML title noise", "cloud deployment"),
    )

    result = TopicLabelingService(max_keywords=3).label_cluster(cluster)

    assert result.keywords == ("cloud", "deployment")
    assert "security" not in result.keywords
    assert "html" not in result.keywords
