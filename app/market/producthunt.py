from app.market.base import MarketConnector


class ProductHuntMarketConnector(MarketConnector):
    def search(self, query: str) -> list[dict]:
        raise NotImplementedError("Implement Product Hunt solution search.")
