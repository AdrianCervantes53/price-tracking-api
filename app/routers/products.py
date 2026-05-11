from fastapi import APIRouter, Depends, status

from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.products import ProductResponse, RegisterProductRequest
from app.services import product_service

router = APIRouter()


def _to_response(product) -> ProductResponse:
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


@router.post(
    "",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Subscribe to a product — upserts the product and creates a subscription",
)
async def register_product(
    body: RegisterProductRequest,
    current_user: User = Depends(get_current_user),
):
    product = await product_service.register_product(
        user_id=str(current_user.id),
        external_id=body.external_id,
        source=body.source,
    )
    return _to_response(product)


@router.get(
    "",
    response_model=list[ProductResponse],
    summary="List products the current user is subscribed to",
)
async def list_products(current_user: User = Depends(get_current_user)):
    products = await product_service.list_products(user_id=str(current_user.id))
    return [_to_response(p) for p in products]


@router.get(
    "/{product_id}",
    response_model=ProductResponse,
    summary="Get product detail — requires an active subscription",
)
async def get_product(
    product_id: str,
    current_user: User = Depends(get_current_user),
):
    product = await product_service.get_product(
        user_id=str(current_user.id),
        product_id=product_id,
    )
    return _to_response(product)


@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unsubscribe from a product — product and price history are preserved",
)
async def delete_subscription(
    product_id: str,
    current_user: User = Depends(get_current_user),
):
    await product_service.unsubscribe(
        user_id=str(current_user.id),
        product_id=product_id,
    )
