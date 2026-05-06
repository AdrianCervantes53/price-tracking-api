from pydantic import BaseModel


class ExternalProductResult(BaseModel):
    external_id: str
    source: str
    name: str
    price: float
    currency: str

