import pytest

from app.clustering.llm_labeling import LLMTopicLabelingService
from app.clustering.schemas import ClusterableDocument
from app.clustering.service import DocumentCluster
from app.llm.client import LLMRequestError


class FakeClient:
    def __init__(self, answer: str | Exception) -> None:
        self.answer = answer
        self.calls: list[list[dict[str, str]]] = []

    def complete(self, messages, response_format=None, temperature=0.0) -> str:
        self.calls.append(messages)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def _document(document_id: int, text: str, x: float) -> ClusterableDocument:
    return ClusterableDocument(
        id=document_id,
        source="hackernews",
        external_id=str(document_id),
        document_text=text,
        embedding=(x,) + (0.0,) * 383,
        embedding_model="model",
    )


CLUSTER = DocumentCluster(
    cluster_id=4,
    documents=(
        _document(1, "I re-type invoice numbers from CSV exports every week", 1.0),
        _document(2, "Copying invoice data from csv into our ERP takes hours", 1.1),
        _document(3, "Invoice reconciliation from CSV is all manual for us", 0.9),
        _document(4, "Outlier post about invoices", 5.0),
    ),
)


def test_uses_the_llm_sentence_and_keeps_keywords() -> None:
    client = FakeClient('"Finance teams re-key invoice data from CSV exports by hand."\n')

    label = LLMTopicLabelingService(client).label_cluster(CLUSTER)  # type: ignore[arg-type]

    assert label.cluster_id == 4
    assert label.label == "Finance teams re-key invoice data from CSV exports by hand"
    assert "invoice" in label.keywords


def test_sends_the_documents_closest_to_the_centroid() -> None:
    client = FakeClient("Teams reconcile invoices by hand")

    LLMTopicLabelingService(client, representative_documents=3).label_cluster(CLUSTER)  # type: ignore[arg-type]

    prompt = client.calls[0][1]["content"]
    assert "Outlier post" not in prompt
    assert prompt.count("Post ") == 3


@pytest.mark.parametrize("answer", [LLMRequestError("down"), "   \n  "])
def test_falls_back_to_keyword_label(answer) -> None:
    label = LLMTopicLabelingService(FakeClient(answer)).label_cluster(CLUSTER)  # type: ignore[arg-type]

    assert label.label == ", ".join(label.keywords)


def test_factory_selects_the_labeling_backend() -> None:
    from dataclasses import replace

    from app.clustering.factory import build_cluster_labeler
    from app.clustering.topic_labeling import TopicLabelingService
    from app.config import settings

    assert isinstance(
        build_cluster_labeler(replace(settings, labeling_backend="keywords")),
        TopicLabelingService,
    )
    assert isinstance(
        build_cluster_labeler(replace(settings, labeling_backend="llm", llm_model="m")),
        LLMTopicLabelingService,
    )
    with pytest.raises(ValueError, match="LLM_MODEL"):
        build_cluster_labeler(replace(settings, labeling_backend="llm", llm_model=None))
