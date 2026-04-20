from datetime import datetime, timezone

from beanie import Document
from pydantic import Field


class Subscription(Document):
    user_id: str   # string ObjectId referencing User
    product_id: str  # string ObjectId referencing Product
    subscribed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "subscriptions"
