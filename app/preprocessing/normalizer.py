from app.ingestion.schemas import SourceItem


def build_document_text(item: SourceItem) -> str:
    parts = [item.title.strip(), item.body.strip()]
    return "\n\n".join(part for part in parts if part)
