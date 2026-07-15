from abc import ABC, abstractmethod


class MarketConnector(ABC):
    @abstractmethod
    def search(self, query: str) -> list[dict]:
        raise NotImplementedError
