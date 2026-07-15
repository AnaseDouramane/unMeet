from app.market.base import MarketConnector


class GitHubMarketConnector(MarketConnector):
    def search(self, query: str) -> list[dict]:
        raise NotImplementedError("Implement GitHub solution search.")
