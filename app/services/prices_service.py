from app.external_clients import get_client
from app.models.price_history import PriceHistory
from app.models.product import Product
from app.repositories.price_history_repository import PriceHistoryRepository
from app.repositories.product_repository import ProductRepository
from app.services import product_service

_product_repo = ProductRepository()
_price_history_repo = PriceHistoryRepository()


async def get_history(user_id: str, product_id: str) -> list[PriceHistory]:
    """
    Returns full price history for a product ordered by timestamp descending.
    Raises HTTP 404 if the product does not exist or the user is not subscribed.
    """
    product = await product_service.get_product(user_id, product_id)
    return await _price_history_repo.get_by_product(str(product.id))


async def refresh(user_id: str, product_id: str) -> Product:
    """
    Fetches the current price from the external API using the product's source,
    updates the product document, and records a new PriceHistory snapshot
    regardless of whether the price changed.
    Raises HTTP 404 if the product does not exist or the user is not subscribed.
    """
    product = await product_service.get_product(user_id, product_id)

    client = get_client(product.source)
    external_data = await client.get_product(product.external_id)

    updated_product = await _product_repo.update_price(product, external_data.price)
    await _price_history_repo.create_snapshot(
        product_id=str(updated_product.id),
        price=updated_product.current_price,
    )

    return updated_product
