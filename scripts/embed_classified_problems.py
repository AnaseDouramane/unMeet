from __future__ import annotations

import sys
from dataclasses import dataclass
from time import perf_counter
from typing import Protocol

from app.config import Settings
from app.database.schemas import PersistedSourceItem
from app.embeddings.embedding_service import EmbeddingService


class EmbeddingStore(Protocol):
    def find_classified_problems_without_embeddings(self) -> list[PersistedSourceItem]: ...

    def save_embedding(self, source_item_id: int, embedding: list[float], embedding_model: str) -> None: ...


@dataclass(frozen=True)
class EmbeddingReport:
    selected: int = 0
    embedded: int = 0
    errors: int = 0


def embed_classified_problems(repository: EmbeddingStore, embedding_service: EmbeddingService) -> EmbeddingReport:
    documents = repository.find_classified_problems_without_embeddings()
    embedded = errors = 0
    total = len(documents)
    for index, document in enumerate(documents, start=1):
        try:
            text = document.document_text
            if not text or not text.strip():
                raise ValueError("document_text is empty")
            repository.save_embedding(document.id, embedding_service.encode(text), embedding_service.model_name)
            embedded += 1
        except Exception as error:
            errors += 1
            print(f"Errore embedding {document.source}/{document.external_id}: {error}", file=sys.stderr)
        print(f"Embedding: {index}/{total}")
    return EmbeddingReport(selected=total, embedded=embedded, errors=errors)


def main() -> int:
    from app.database.repository import SourceItemRepository

    started_at = perf_counter()
    try:
        report = embed_classified_problems(
            SourceItemRepository(), EmbeddingService(model_name=Settings().embedding_model)
        )
    except Exception as error:
        print(f"Errore embedding: {error}", file=sys.stderr)
        return 1
    print(
        f"Selezionati: {report.selected}\nEmbedding generati: {report.embedded}\n"
        f"Errori: {report.errors}\nDurata totale: {perf_counter() - started_at:.2f}s"
    )
    return 0 if report.errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
