from abc import ABC, abstractmethod
from collections.abc import Iterable

from app.ingestion.schemas import SourceItem


class SourceConnector(ABC):
    @abstractmethod
    def fetch(self) -> Iterable[SourceItem]:
        raise NotImplementedError
