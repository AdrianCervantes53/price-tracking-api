from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.dependencies import get_current_user
from app.models.user import User

router = APIRouter()


class PriceHistoryEntry(BaseModel):
    price: float
    timestamp: datetime


@router.get(
    "/{product_id}/history",
    response_model=list[PriceHistoryEntry],
    summary="Get full price history for a product, ordered by date desc",
)
async def get_price_history(
    product_id: str,
    current_user: User = Depends(get_current_user),
):
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED)


@router.post(
    "/{product_id}/refresh",
    response_model=PriceHistoryEntry,
    status_code=status.HTTP_200_OK,
    summary="Fetch current price from external API and record a new snapshot",
)
async def refresh_price(
    product_id: str,
    current_user: User = Depends(get_current_user),
):
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED)
