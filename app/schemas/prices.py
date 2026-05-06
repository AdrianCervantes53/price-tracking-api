from datetime import datetime

from pydantic import BaseModel


class PriceHistoryEntry(BaseModel):
    price: float
    timestamp: datetime

