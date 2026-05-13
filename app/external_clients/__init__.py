from app.external_clients.fake_store_client import FakeStoreClient
from app.external_clients.mercadolibre_client import MercadoLibreClient


def get_client(source: str) -> FakeStoreClient | MercadoLibreClient:
    """Returns the correct external API client for the given source."""
    if source == "fakestore":
        return FakeStoreClient()
    if source == "mercadolibre":
        return MercadoLibreClient()
    raise ValueError(f"Unknown source: '{source}'")
