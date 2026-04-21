from datetime import datetime, timezone

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, IndexModel


class Product(Document):
    external_id: str
    source: str  # "fakestore" | "mercadolibre"
    name: str
    current_price: float
    currency: str
    availability: bool = True
    last_checked: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "products"
        indexes = [
            IndexModel(
                [("external_id", ASCENDING), ("source", ASCENDING)],
                unique=True,
            )
        ]
