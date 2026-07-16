from app.ingestion.schemas import SourceItem


def build_document_text(title: str, body: str) -> str:
    parts = [title.strip(), body.strip()]
    return "\n\n".join(part for part in parts if part)
