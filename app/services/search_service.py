from app.external_clients.fake_store_client import FakeStoreClient
from app.schemas.search import ExternalProductResult

_client = FakeStoreClient()


async def search_products(q: str) -> list[ExternalProductResult]:
    return await _client.search(q)
