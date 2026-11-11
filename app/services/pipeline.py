from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from app.config import Settings
from app.database.repository import SourceItemRepository
from app.embeddings.embedding_service import EmbeddingService
from app.ingestion.base import SourceConnector
from app.ingestion.hackernews import HackerNewsConnector
from app.ingestion.schemas import SourceItem
from app.preprocessing.schemas import PreparedDocument
from app.privacy.service import ErasureFilter
from app.problem_detection.schemas import ProblemDetectionResult, TopicContext
from app.problem_detection.service import ProblemDetectionService
from app.services.preprocessing import PreprocessingService
from app.topics.gate import GATE_CLASSIFIER_NAME, GateDecision, TopicGate


@dataclass(frozen=True)
class PipelineRunStats:
    acquired_count: int
    problem_count: int
    non_problem_count: int
    embedding_count: int
    classification_error_count: int
    skipped_count: int = 0
    gated_out_count: int = 0
    suppressed_count: int = 0
    llm_call_count: int = 0
    matched_count: int = 0


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
        topic_gate: TopicGate | None = None,
        classification_batch_size: int = 1,
        erasure_filter: ErasureFilter | None = None,
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
        if (
            isinstance(classification_batch_size, bool)
            or not isinstance(classification_batch_size, int)
            or classification_batch_size <= 0
        ):
            raise ValueError("classification_batch_size must be a positive integer")
        self.classification_workers = classification_workers
        self.classification_batch_size = classification_batch_size
        self.topic_gate = topic_gate
        self.erasure_filter = erasure_filter
        self.last_run_stats: PipelineRunStats | None = None
        self._accepted: list[PreparedDocument] = []
        self._counts: dict[str, int] = {}

    def run(self, connector: SourceConnector | None = None) -> list[PreparedDocument]:
        self.last_run_stats = None

        self._accepted = []
        self._counts = {
            "acquired": 0,
            "non_problem": 0,
            "errors": 0,
            "skipped": 0,
            "gated_out": 0,
            "suppressed": 0,
            "matched": 0,
            "llm_calls": 0,
        }
        if self.topic_gate is not None:
            self.topic_gate.begin_run()
        if self.erasure_filter is not None:
            self.erasure_filter.refresh()
        active_connector = connector or self.connector
        batch_size = self.classification_workers * 8
        pending: list[tuple[SourceItem, PreparedDocument]] = []
        try:
            for source_item in active_connector.fetch():
                self._counts["acquired"] += 1
                if self.erasure_filter is not None and self.erasure_filter.is_suppressed(
                    source_item.source, source_item.author
                ):
                    self._counts["suppressed"] += 1
                    continue
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
            gated_out_count=self._counts["gated_out"],
            suppressed_count=self._counts["suppressed"],
            matched_count=self._counts["matched"],
            llm_call_count=self._counts["llm_calls"],
        )
        return accepted_documents

    def _process_batch(self, batch: list[tuple[SourceItem, PreparedDocument]]) -> None:
        """Classify a batch (concurrently if configured), then persist it in source order.

        Batching bounds memory and keeps partial progress if a connector fails mid-stream.
        """
        if not batch:
            return
        decisions: list[GateDecision | None] = [
            self.topic_gate.evaluate(document.document_text) if self.topic_gate else None
            for _, document in batch
        ]
        to_classify = [
            document
            for (_, document), decision in zip(batch, decisions, strict=True)
            if decision is None or decision.passed
        ]
        topics_to_classify: list[tuple[TopicContext, ...]] = [
            self.topic_gate.topic_contexts(decision.matched_topic_ids)
            if self.topic_gate is not None and decision is not None
            else ()
            for decision in decisions
            if decision is None or decision.passed
        ]
        requests_before = getattr(self.problem_detection_service, "llm_request_count", None)
        classified = iter(list(self._classify(iter(to_classify), topics_to_classify)))
        requests_after = getattr(self.problem_detection_service, "llm_request_count", None)
        if isinstance(requests_before, int) and isinstance(requests_after, int):
            self._counts["llm_calls"] += requests_after - requests_before
        else:
            self._counts["llm_calls"] += len(to_classify)
        for (source_item, prepared_document), decision in zip(batch, decisions, strict=True):
            if decision is not None and not decision.passed:
                self._counts["gated_out"] += 1
                self._counts["non_problem"] += 1
                self.repository.save(
                    source_item,
                    prepared_document,
                    problem_detection_result=ProblemDetectionResult(
                        is_problem=False,
                        confidence=1.0,
                        reason="No active topic matches this item",
                        classifier_name=GATE_CLASSIFIER_NAME,
                    ),
                )
                continue
            detection_result, malformed = next(classified)
            if malformed:
                self._counts["errors"] += 1
            if detection_result.is_problem:
                embedding = (
                    decision.embedding
                    if decision is not None
                    else self.embedding_service.encode(prepared_document.document_text)
                )
                self.repository.save(
                    source_item,
                    prepared_document,
                    embedding=embedding,
                    embedding_model=self.embedding_service.model_name,
                    problem_detection_result=detection_result,
                )
                self._accepted.append(prepared_document)
                if detection_result.topic_matches:
                    self._counts["matched"] += 1
                continue
            self.repository.save(
                source_item,
                prepared_document,
                problem_detection_result=detection_result,
            )
            self._counts["non_problem"] += 1

    def _classify(
        self,
        documents: Iterator[PreparedDocument],
        topics: Sequence[tuple[TopicContext, ...]] = (),
    ) -> Iterator[tuple[ProblemDetectionResult, bool]]:
        """Classify documents in input order, concurrently when workers are configured.

        API-backed classifiers spend most of their time waiting on the network, so a small
        thread pool gives a near-linear speed-up while results stay in source order.
        """
        if any(topics) and getattr(
            self.problem_detection_service, "supports_topic_matching", False
        ):
            yield from self._classify_with_topics(list(documents), topics)
            return
        batch_detect = getattr(self.problem_detection_service, "detect_batch_with_status", None)
        if (
            self.classification_batch_size > 1
            and callable(batch_detect)
            and getattr(self.problem_detection_service, "supports_batching", False)
        ):
            yield from self._classify_in_batches(documents, batch_detect)
            return
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

    def _classify_with_topics(
        self,
        documents: list[PreparedDocument],
        topics: Sequence[tuple[TopicContext, ...]],
    ) -> Iterator[tuple[ProblemDetectionResult, bool]]:
        """Classify documents together with the candidate topics the gate found for each."""
        service = self.problem_detection_service
        size = self.classification_batch_size if getattr(service, "supports_batching", False) else 1
        jobs = [
            (documents[start : start + size], list(topics[start : start + size]))
            for start in range(0, len(documents), size)
        ]

        def run(job: tuple[list[PreparedDocument], list[tuple[TopicContext, ...]]]):
            chunk, chunk_topics = job
            if size > 1:
                return service.detect_batch_with_status(chunk, chunk_topics)
            return [service.detect_with_status(chunk[0], chunk_topics[0])]

        if self.classification_workers == 1 or len(jobs) <= 1:
            for job in jobs:
                yield from run(job)
            return
        with ThreadPoolExecutor(max_workers=self.classification_workers) as executor:
            for results in executor.map(run, jobs):
                yield from results

    def _classify_in_batches(
        self,
        documents: Iterator[PreparedDocument],
        batch_detect: Callable[[list[PreparedDocument]], list[tuple[ProblemDetectionResult, bool]]],
    ) -> Iterator[tuple[ProblemDetectionResult, bool]]:
        """Send documents to the model several per request, keeping input order."""
        pending = list(documents)
        size = self.classification_batch_size
        chunks = [pending[start : start + size] for start in range(0, len(pending), size)]
        if self.classification_workers == 1 or len(chunks) <= 1:
            for chunk in chunks:
                yield from batch_detect(chunk)
            return
        with ThreadPoolExecutor(max_workers=self.classification_workers) as executor:
            for results in executor.map(batch_detect, chunks):
                yield from results

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
        if getattr(existing, "problem_classifier", None) == GATE_CLASSIFIER_NAME:
            # Gated items were never judged by the model: re-check against current topics.
            return False
        return existing.dedup_hash == prepared_document.dedup_hash
