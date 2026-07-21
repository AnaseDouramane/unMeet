from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.ingestion.base import SourceConnector
from app.services.preprocessing import PreprocessingService


class UnclassifiedDocumentStore(Protocol):
    def save_unclassified_if_new(self, source_item, prepared_document) -> bool: ...


@dataclass(frozen=True)
class IngestionOnlyStats:
    acquired_count: int = 0
    new_count: int = 0
    existing_count: int = 0
    error_count: int = 0


class IngestionOnlyService:
    """Fetch and prepare posts without running any model inference."""

    def __init__(self, preprocessing_service: PreprocessingService, repository: UnclassifiedDocumentStore):
        self._preprocessing_service = preprocessing_service
        self._repository = repository

    def run(self, connector: SourceConnector) -> IngestionOnlyStats:
        acquired = new = existing = errors = 0
        try:
            source_items = connector.fetch()
            for source_item in source_items:
                acquired += 1
                try:
                    prepared = self._preprocessing_service.prepare(source_item)
                    if self._repository.save_unclassified_if_new(source_item, prepared):
                        new += 1
                    else:
                        existing += 1
                except Exception:
                    errors += 1
        except Exception:
            # The caller reports connector-level failures; preserve any item progress.
            raise
        return IngestionOnlyStats(acquired, new, existing, errors)
