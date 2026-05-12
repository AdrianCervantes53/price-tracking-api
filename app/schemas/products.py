from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class RegisterProductRequest(BaseModel):
    external_id: str
    source: Literal["fakestore", "mercadolibre"] = "fakestore"


class ProductResponse(BaseModel):
    id: str
    external_id: str
    source: str
    name: str
    current_price: float
    currency: str
    availability: bool
    last_checked: datetime
