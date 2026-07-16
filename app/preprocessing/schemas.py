from dataclasses import dataclass

from app.ingestion.schemas import SourceItem


@dataclass
class PreparedDocument:
    source_item: SourceItem
    title: str
    body: str
    document_text: str
    dedup_hash: str
