from app.models.price_history import PriceHistory


class PriceHistoryRepository:
    async def create_snapshot(self, product_id: str, price: float) -> PriceHistory:
        snapshot = PriceHistory(product_id=product_id, price=price)
        await snapshot.insert()
        return snapshot

    async def get_by_product(self, product_id: str) -> list[PriceHistory]:
        """Returns all snapshots for a product ordered by timestamp descending."""
        return (
            await PriceHistory.find(PriceHistory.product_id == product_id)
            .sort("-timestamp")
            .to_list()
        )
