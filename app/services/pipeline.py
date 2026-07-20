from dataclasses import dataclass

from app.config import Settings
from app.database.repository import SourceItemRepository
from app.embeddings.embedding_service import EmbeddingService
from app.ingestion.hackernews import HackerNewsConnector
from app.preprocessing.schemas import PreparedDocument
from app.problem_detection.service import ProblemDetectionService
from app.services.preprocessing import PreprocessingService


@dataclass(frozen=True)
class PipelineRunStats:
    acquired_count: int
    problem_count: int
    non_problem_count: int
    embedding_count: int


class Pipeline:
    def __init__(
        self,
        settings: Settings,
        connector: HackerNewsConnector,
        preprocessing_service: PreprocessingService,
        problem_detection_service: ProblemDetectionService,
        embedding_service: EmbeddingService,
        repository: SourceItemRepository,
    ) -> None:
        self.settings = settings
        self.connector = connector
        self.preprocessing_service = preprocessing_service
        self.repository = repository
        self.embedding_service = embedding_service
        self.problem_detection_service = problem_detection_service
        self.last_run_stats: PipelineRunStats | None = None

    def run(self) -> list[PreparedDocument]:
        self.last_run_stats = None

        accepted_documents: list[PreparedDocument] = []
        acquired_count = 0
        non_problem_count = 0
        for source_item in self.connector.fetch():
            acquired_count += 1
            prepared_document = self.preprocessing_service.prepare(source_item)
            detection_result = self.problem_detection_service.detect(prepared_document)
            if detection_result.is_problem:
                embedding = self.embedding_service.encode(prepared_document.document_text)
                self.repository.save(
                    source_item,
                    prepared_document,
                    embedding=embedding,
                    embedding_model=self.embedding_service.model_name,
                    problem_detection_result=detection_result,
                )
                accepted_documents.append(prepared_document)
                continue

            self.repository.save(
                source_item,
                prepared_document,
                problem_detection_result=detection_result,
            )
            non_problem_count += 1
        self.last_run_stats = PipelineRunStats(
            acquired_count=acquired_count,
            problem_count=len(accepted_documents),
            non_problem_count=non_problem_count,
            embedding_count=len(accepted_documents),
        )
        return accepted_documents
