from app.config import Settings
from app.ingestion.hackernews import HackerNewsConnector
from app.preprocessing.schemas import PreparedDocument
from app.services.preprocessing import PreprocessingService


class Pipeline:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.connector = HackerNewsConnector(limit=10)
        self.preprocessing_service = PreprocessingService()

    def run(self) -> list[PreparedDocument]:
        source_items = list(self.connector.fetch())
        return [self.preprocessing_service.prepare(item) for item in source_items]
