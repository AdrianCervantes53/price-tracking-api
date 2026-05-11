from bson.errors import InvalidId
from fastapi import HTTPException, status

from app.external_clients.fake_store_client import FakeStoreClient
from app.models.product import Product
from app.repositories.price_history_repository import PriceHistoryRepository
from app.repositories.product_repository import ProductRepository
from app.repositories.subscription_repository import SubscriptionRepository

_client = FakeStoreClient()
_product_repo = ProductRepository()
_sub_repo = SubscriptionRepository()
_price_history_repo = PriceHistoryRepository()


async def get_product(user_id: str, product_id: str) -> Product:
    """
    Returns the product if the user has an active subscription.
    Raises HTTP 404 in all failure cases — invalid ID, product not found,
    or no active subscription — to avoid revealing whether a product exists.
    """
    try:
        product = await _product_repo.get_by_id(product_id)
    except (InvalidId, ValueError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    subscription = await _sub_repo.get_by_user_and_product(user_id, str(product.id))
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    return product


async def register_product(user_id: str, external_id: str, source: str) -> Product:
    """
    Upserts the product by (external_id, source) and creates a subscription
    for the authenticated user. If the product is new, records the first
    PriceHistory snapshot. Raises HTTP 409 if already subscribed.
    """
    external_data = await _client.get_product(external_id)

    product, is_new = await _product_repo.upsert(
        external_id=external_id,
        source=source,
        name=external_data.name,
        price=external_data.price,
        currency=external_data.currency,
    )

    product_id = str(product.id)
    existing_sub = await _sub_repo.get_by_user_and_product(user_id, product_id)
    if existing_sub:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Already subscribed to this product",
        )

    await _sub_repo.create(user_id=user_id, product_id=product_id)

    if is_new:
        await _price_history_repo.create_snapshot(
            product_id=product_id,
            price=product.current_price,
        )

    return product


async def list_products(user_id: str) -> list[Product]:
    return await _sub_repo.get_subscribed_products(user_id)


async def unsubscribe(user_id: str, product_id: str) -> None:
    """
    Removes the user's subscription. The product and its price history
    are preserved. Raises HTTP 404 if no active subscription exists.
    """
    deleted = await _sub_repo.delete(user_id=user_id, product_id=product_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )
