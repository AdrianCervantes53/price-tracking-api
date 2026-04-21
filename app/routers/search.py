from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.core.dependencies import get_current_user
from app.models.user import User

router = APIRouter()


class ExternalProductResult(BaseModel):
    external_id: str
    source: str
    name: str
    price: float
    currency: str


@router.get(
    "",
    response_model=list[ExternalProductResult],
    summary="Search products in external marketplace (results not persisted)",
)
async def search_products(
    q: str = Query(..., min_length=1, description="Search term"),
    current_user: User = Depends(get_current_user),
):
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED)
