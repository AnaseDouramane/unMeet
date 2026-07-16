from app.config import Settings
from app.database.repository import SourceItemRepository
from app.ingestion.hackernews import HackerNewsConnector
from app.preprocessing.schemas import PreparedDocument
from app.services.preprocessing import PreprocessingService


class Pipeline:
    def __init__(self, settings: Settings, repository: SourceItemRepository | None = None) -> None:
        self.settings = settings
        self.connector = HackerNewsConnector(limit=10)
        self.preprocessing_service = PreprocessingService()
        self.repository = repository or SourceItemRepository()

    def run(self) -> list[PreparedDocument]:
        source_items = list(self.connector.fetch())
        prepared_documents = [self.preprocessing_service.prepare(item) for item in source_items]
        for source_item, prepared_document in zip(source_items, prepared_documents, strict=True):
            self.repository.save(source_item, prepared_document)
        return prepared_documents
