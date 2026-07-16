from app.ingestion.schemas import SourceItem
from app.preprocessing.cleaner import clean_text
from app.preprocessing.deduplicator import text_hash
from app.preprocessing.normalizer import build_document_text
from app.preprocessing.schemas import PreparedDocument


class PreprocessingService:
    def prepare(self, source_item: SourceItem) -> PreparedDocument:
        title = clean_text(source_item.title)
        body = clean_text(source_item.body)
        document_text = build_document_text(title, body)
        dedup_hash = text_hash(document_text)
        return PreparedDocument(
            source_item=source_item,
            title=title,
            body=body,
            document_text=document_text,
            dedup_hash=dedup_hash,
        )
