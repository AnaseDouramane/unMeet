from dataclasses import dataclass


@dataclass(frozen=True)
class ClusterableDocument:
    id: int
    source: str
    external_id: str
    document_text: str
    embedding: tuple[float, ...]
    embedding_model: str
