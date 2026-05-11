from app.models.price_history import PriceHistory


class PriceHistoryRepository:
    async def create_snapshot(self, product_id: str, price: float) -> PriceHistory:
        snapshot = PriceHistory(product_id=product_id, price=price)
        await snapshot.insert()
        return snapshot
