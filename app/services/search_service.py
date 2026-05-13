from app.external_clients import get_client
from app.schemas.search import ExternalProductResult


async def search_products(q: str, source: str) -> list[ExternalProductResult]:
    return await get_client(source).search(q)
