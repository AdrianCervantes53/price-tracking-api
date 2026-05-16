from app.external_clients.coingecko_client import CoinGeckoClient
from app.external_clients.fake_store_client import FakeStoreClient
from app.external_clients.finnhub_client import FinnhubClient
from app.external_clients.mercadolibre_client import MercadoLibreClient


def get_client(
    source: str,
) -> CoinGeckoClient | FakeStoreClient | FinnhubClient | MercadoLibreClient:
    """
    Returns the correct external API client for the given source.

    Active sources: "fakestore", "coingecko"
    Reference only (not exposed in public API):
      - "finnhub"      — retained as implementation reference; ToS prohibits redistribution
      - "mercadolibre" — retained as implementation reference; API returns 403 as of 2024–2025
    """
    if source == "fakestore":
        return FakeStoreClient()
    if source == "coingecko":
        return CoinGeckoClient()
    if source == "finnhub":
        return FinnhubClient()
    if source == "mercadolibre":
        return MercadoLibreClient()
    raise ValueError(f"Unknown source: '{source}'")
