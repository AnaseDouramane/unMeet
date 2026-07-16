from datetime import datetime, timezone

from app.ingestion.schemas import SourceItem
from app.preprocessing.cleaner import clean_text
from app.preprocessing.deduplicator import text_hash
from app.preprocessing.normalizer import build_document_text
from app.services.preprocessing import PreprocessingService


def test_preprocessing_service_prepares_document_without_mutating_source_item() -> None:
    source_item = SourceItem(
        external_id="123",
        source="hackernews",
        title="Hello <b>HN</b>",
        body="<p>Body <i>content</i></p>",
        url="https://example.com/article",
        author="alice",
        published_at=datetime.fromtimestamp(1_700_000_000, tz=timezone.utc),
        engagement_score=42,
        raw_payload={"id": 123, "type": "story"},
    )

    original_title = source_item.title
    original_body = source_item.body

    service = PreprocessingService()
    prepared = service.prepare(source_item)

    assert source_item.title == original_title
    assert source_item.body == original_body
    assert prepared.source_item is source_item
    assert prepared.title == clean_text(original_title)
    assert prepared.body == clean_text(original_body)
    assert prepared.document_text == build_document_text(prepared.title, prepared.body)
    assert prepared.dedup_hash == text_hash(prepared.document_text)
    assert prepared.document_text == "Hello HN\n\nBody content"
