from datetime import datetime

from pydantic import BaseModel


class RegisterProductRequest(BaseModel):
    external_id: str
    source: str


class ProductResponse(BaseModel):
    id: str
    external_id: str
    source: str
    name: str
    current_price: float
    currency: str
    availability: bool
    last_checked: datetime

