from datetime import datetime, timezone

from beanie import Document
from pydantic import Field


class PriceHistory(Document):
    product_id: str  # string ObjectId referencing Product
    price: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "price_history"
