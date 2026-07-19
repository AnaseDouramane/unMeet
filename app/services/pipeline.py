from app.config import Settings
from app.database.repository import SourceItemRepository
from app.embeddings.embedding_service import EmbeddingService
from app.ingestion.hackernews import HackerNewsConnector
from app.preprocessing.schemas import PreparedDocument
from app.services.preprocessing import PreprocessingService


class Pipeline:
    def __init__(
        self,
        settings: Settings,
        repository: SourceItemRepository | None = None,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        self.settings = settings
        self.connector = HackerNewsConnector(limit=10)
        self.preprocessing_service = PreprocessingService()
        self.repository = repository or SourceItemRepository()
        self.embedding_service = embedding_service or EmbeddingService()

    def run(self) -> list[PreparedDocument]:
        source_items = list(self.connector.fetch())
        prepared_documents = [self.preprocessing_service.prepare(item) for item in source_items]
        embeddings = [
            self.embedding_service.encode(document.document_text) for document in prepared_documents
        ]
        for source_item, prepared_document, embedding in zip(
            source_items,
            prepared_documents,
            embeddings,
            strict=True,
        ):
            self.repository.save(
                source_item,
                prepared_document,
                embedding=embedding,
                embedding_model=self.embedding_service.model_name,
            )
        return prepared_documents
