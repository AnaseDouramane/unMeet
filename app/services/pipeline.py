from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from app.config import Settings
from app.database.repository import SourceItemRepository
from app.embeddings.embedding_service import EmbeddingService
from app.ingestion.base import SourceConnector
from app.ingestion.hackernews import HackerNewsConnector
from app.ingestion.schemas import SourceItem
from app.preprocessing.schemas import PreparedDocument
from app.problem_detection.schemas import ProblemDetectionResult
from app.problem_detection.service import ProblemDetectionService
from app.services.preprocessing import PreprocessingService


@dataclass(frozen=True)
class PipelineRunStats:
    acquired_count: int
    problem_count: int
    non_problem_count: int
    embedding_count: int
    classification_error_count: int
    skipped_count: int = 0


class Pipeline:
    def __init__(
        self,
        settings: Settings,
        connector: HackerNewsConnector,
        preprocessing_service: PreprocessingService,
        problem_detection_service: ProblemDetectionService,
        embedding_service: EmbeddingService,
        repository: SourceItemRepository,
        classification_workers: int = 1,
    ) -> None:
        if (
            isinstance(classification_workers, bool)
            or not isinstance(classification_workers, int)
            or classification_workers <= 0
        ):
            raise ValueError("classification_workers must be a positive integer")
        self.settings = settings
        self.connector = connector
        self.preprocessing_service = preprocessing_service
        self.repository = repository
        self.embedding_service = embedding_service
        self.problem_detection_service = problem_detection_service
        self.classification_workers = classification_workers
        self.last_run_stats: PipelineRunStats | None = None
        self._accepted: list[PreparedDocument] = []
        self._counts: dict[str, int] = {}

    def run(self, connector: SourceConnector | None = None) -> list[PreparedDocument]:
        self.last_run_stats = None

        self._accepted = []
        self._counts = {"acquired": 0, "non_problem": 0, "errors": 0, "skipped": 0}
        active_connector = connector or self.connector
        batch_size = self.classification_workers * 8
        pending: list[tuple[SourceItem, PreparedDocument]] = []
        try:
            for source_item in active_connector.fetch():
                self._counts["acquired"] += 1
                prepared_document = self.preprocessing_service.prepare(source_item)
                if self._is_already_classified(source_item, prepared_document):
                    self._counts["skipped"] += 1
                    continue
                pending.append((source_item, prepared_document))
                if len(pending) >= batch_size:
                    batch, pending = pending, []
                    self._process_batch(batch)
        finally:
            # Persist what was already fetched even when the connector fails mid-stream.
            batch, pending = pending, []
            self._process_batch(batch)

        accepted_documents = self._accepted
        self.last_run_stats = PipelineRunStats(
            acquired_count=self._counts["acquired"],
            problem_count=len(accepted_documents),
            non_problem_count=self._counts["non_problem"],
            embedding_count=len(accepted_documents),
            classification_error_count=self._counts["errors"],
            skipped_count=self._counts["skipped"],
        )
        return accepted_documents

    def _process_batch(self, batch: list[tuple[SourceItem, PreparedDocument]]) -> None:
        """Classify a batch (concurrently if configured), then persist it in source order.

        Batching bounds memory and keeps partial progress if a connector fails mid-stream.
        """
        if not batch:
            return
        results = self._classify(iter([document for _, document in batch]))
        for (source_item, prepared_document), (detection_result, malformed) in zip(
            batch, results, strict=True
        ):
            if malformed:
                self._counts["errors"] += 1
            if detection_result.is_problem:
                embedding = self.embedding_service.encode(prepared_document.document_text)
                self.repository.save(
                    source_item,
                    prepared_document,
                    embedding=embedding,
                    embedding_model=self.embedding_service.model_name,
                    problem_detection_result=detection_result,
                )
                self._accepted.append(prepared_document)
                continue
            self.repository.save(
                source_item,
                prepared_document,
                problem_detection_result=detection_result,
            )
            self._counts["non_problem"] += 1

    def _classify(
        self, documents: Iterator[PreparedDocument]
    ) -> Iterator[tuple[ProblemDetectionResult, bool]]:
        """Classify documents in input order, concurrently when workers are configured.

        API-backed classifiers spend most of their time waiting on the network, so a small
        thread pool gives a near-linear speed-up while results stay in source order.
        """
        concurrent_detect = getattr(self.problem_detection_service, "detect_with_status", None)
        if self.classification_workers == 1 or concurrent_detect is None:
            for document in documents:
                result = self.problem_detection_service.detect(document)
                malformed = bool(
                    getattr(
                        self.problem_detection_service,
                        "last_detection_was_malformed_output",
                        False,
                    )
                )
                yield result, malformed
            return
        with ThreadPoolExecutor(max_workers=self.classification_workers) as executor:
            yield from executor.map(concurrent_detect, documents)

    def _is_already_classified(
        self, source_item: SourceItem, prepared_document: PreparedDocument
    ) -> bool:
        """Return True when the same content was already classified in a previous run.

        Re-classifying unchanged items wastes model time (and API cost for hosted models).
        Edited items, detected through a different dedup hash, are classified again.
        """
        lookup = getattr(self.repository, "get_by_source_and_external_id", None)
        if lookup is None:
            return False
        existing = lookup(source_item.source, source_item.external_id)
        if existing is None or existing.is_problem is None:
            return False
        return existing.dedup_hash == prepared_document.dedup_hash
