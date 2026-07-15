from typing import Iterable

from app.ingestion.base import SourceConnector
from app.ingestion.schemas import SourceItem


class RedditConnector(SourceConnector):
    def fetch(self) -> Iterable[SourceItem]:
        raise NotImplementedError("Implement Reddit API ingestion.")
