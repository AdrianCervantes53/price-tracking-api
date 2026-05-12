from fastapi import APIRouter, Depends, status

from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.prices import PriceHistoryEntry
from app.schemas.products import ProductResponse
from app.services import prices_service

router = APIRouter()


@router.get(
    "/{product_id}/history",
    response_model=list[PriceHistoryEntry],
    summary="Get full price history for a product, ordered by date desc",
)
async def get_price_history(
    product_id: str,
    current_user: User = Depends(get_current_user),
):
    entries = await prices_service.get_history(
        user_id=str(current_user.id),
        product_id=product_id,
    )
    return [PriceHistoryEntry(price=e.price, timestamp=e.timestamp) for e in entries]


@router.post(
    "/{product_id}/refresh",
    response_model=ProductResponse,
    status_code=status.HTTP_200_OK,
    summary="Fetch current price from external API and record a new snapshot",
)
async def refresh_price(
    product_id: str,
    current_user: User = Depends(get_current_user),
):
    product = await prices_service.refresh(
        user_id=str(current_user.id),
        product_id=product_id,
    )
    return ProductResponse(
        id=str(product.id),
        external_id=product.external_id,
        source=product.source,
        name=product.name,
        current_price=product.current_price,
        currency=product.currency,
        availability=product.availability,
        last_checked=product.last_checked,
    )
