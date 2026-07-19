from app.config import Settings
from app.database.repository import SourceItemRepository
from app.embeddings.embedding_service import EmbeddingService
from app.ingestion.hackernews import HackerNewsConnector
from app.preprocessing.schemas import PreparedDocument
from app.problem_detection.service import ProblemDetectionService
from app.services.preprocessing import PreprocessingService


class Pipeline:
    def __init__(
        self,
        settings: Settings,
        repository: SourceItemRepository | None = None,
        embedding_service: EmbeddingService | None = None,
        problem_detection_service: ProblemDetectionService | None = None,
    ) -> None:
        self.settings = settings
        self.connector = HackerNewsConnector(limit=10)
        self.preprocessing_service = PreprocessingService()
        self.repository = repository or SourceItemRepository()
        self.embedding_service = embedding_service or EmbeddingService()
        self.problem_detection_service = problem_detection_service

    def run(self) -> list[PreparedDocument]:
        if self.problem_detection_service is None:
            raise RuntimeError("Pipeline requires an injected ProblemDetectionService")

        accepted_documents: list[PreparedDocument] = []
        for source_item in self.connector.fetch():
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
        return accepted_documents
