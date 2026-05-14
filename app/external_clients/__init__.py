from app.external_clients.fake_store_client import FakeStoreClient
from app.external_clients.finnhub_client import FinnhubClient
from app.external_clients.mercadolibre_client import MercadoLibreClient


def get_client(source: str) -> FakeStoreClient | FinnhubClient | MercadoLibreClient:
    """
    Returns the correct external API client for the given source.

    Active sources: "fakestore", "finnhub"
    Deprecated: "mercadolibre" — client is retained for reference but the
    MercadoLibre API returns 403 on all public endpoints as of 2024–2025.
    """
    if source == "fakestore":
        return FakeStoreClient()
    if source == "finnhub":
        return FinnhubClient()
    if source == "mercadolibre":
        return MercadoLibreClient()
    raise ValueError(f"Unknown source: '{source}'")
