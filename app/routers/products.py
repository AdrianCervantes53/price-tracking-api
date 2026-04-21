from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.dependencies import get_current_user
from app.models.user import User

router = APIRouter()


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
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED)


@router.get(
    "",
    response_model=list[ProductResponse],
    summary="List products the current user is subscribed to",
)
async def list_products(current_user: User = Depends(get_current_user)):
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED)


@router.get(
    "/{product_id}",
    response_model=ProductResponse,
    summary="Get product detail — requires an active subscription",
)
async def get_product(
    product_id: str,
    current_user: User = Depends(get_current_user),
):
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED)


@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unsubscribe from a product — product and price history are preserved",
)
async def delete_subscription(
    product_id: str,
    current_user: User = Depends(get_current_user),
):
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED)
