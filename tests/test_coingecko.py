"""
Tests for CoinGecko integration:
  - Unit tests for CoinGeckoClient._to_schema adapter
  - Integration tests for GET /search?source=coingecko
  - Integration tests for POST /products with source=coingecko
  - Integration tests for POST /products/{id}/refresh on a CoinGecko product
"""

import httpx
import pytest
import respx

from app.external_clients.coingecko_client import CoinGeckoClient
from app.models.price_history import PriceHistory
from app.models.product import Product
from app.models.subscription import Subscription

# ---------------------------------------------------------------------------
# Fixtures — realistic CoinGecko payloads
# ---------------------------------------------------------------------------

COINGECKO_SEARCH_RESPONSE = {
    "coins": [
        {"id": "bitcoin", "name": "Bitcoin", "symbol": "BTC", "market_cap_rank": 1},
        {"id": "bitcoin-cash", "name": "Bitcoin Cash", "symbol": "BCH", "market_cap_rank": 20},
    ],
    "exchanges": [],
    "nfts": [],
}

COINGECKO_PRICE_RESPONSE = {
    "bitcoin": {"usd": 45000.0},
    "bitcoin-cash": {"usd": 320.0},
}

COINGECKO_COIN_RESPONSE = {
    "id": "bitcoin",
    "symbol": "btc",
    "name": "Bitcoin",
}

BITCOIN_NEW_PRICE = {"bitcoin": {"usd": 47500.0}}


@pytest.fixture
async def auth_headers(client):
    await client.post(
        "/auth/register",
        json={"email": "coingecko@example.com", "password": "securepassword"},
    )
    response = await client.post(
        "/auth/login",
        json={"email": "coingecko@example.com", "password": "securepassword"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Unit tests — _to_schema adapter
# ---------------------------------------------------------------------------


def test_to_schema_maps_fields_correctly():
    result = CoinGeckoClient._to_schema("bitcoin", "Bitcoin", 45000.0)

    assert result.external_id == "bitcoin"
    assert result.source == "coingecko"
    assert result.name == "Bitcoin"
    assert result.price == 45000.0
    assert result.currency == "USD"


def test_to_schema_currency_is_always_usd():
    result = CoinGeckoClient._to_schema("ethereum", "Ethereum", 2500.0)
    assert result.currency == "USD"


# ---------------------------------------------------------------------------
# Integration tests — GET /search?source=coingecko
# ---------------------------------------------------------------------------


@respx.mock
async def test_search_coingecko_returns_results(client, auth_headers):
    """Search should return all coins with price data from CoinGecko."""
    respx.get("https://api.coingecko.com/api/v3/search").mock(
        return_value=httpx.Response(200, json=COINGECKO_SEARCH_RESPONSE)
    )
    respx.get("https://api.coingecko.com/api/v3/simple/price").mock(
        return_value=httpx.Response(200, json=COINGECKO_PRICE_RESPONSE)
    )

    response = await client.get("/search?q=bitcoin&source=coingecko", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["external_id"] == "bitcoin"
    assert data[0]["source"] == "coingecko"
    assert data[0]["price"] == 45000.0
    assert data[0]["currency"] == "USD"


@respx.mock
async def test_search_coingecko_empty_results(client, auth_headers):
    respx.get("https://api.coingecko.com/api/v3/search").mock(
        return_value=httpx.Response(200, json={"coins": [], "exchanges": [], "nfts": []})
    )

    response = await client.get("/search?q=xyznotfound&source=coingecko", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == []


@respx.mock
async def test_search_coingecko_timeout_returns_503(client, auth_headers):
    respx.get("https://api.coingecko.com/api/v3/search").mock(
        side_effect=httpx.TimeoutException("timed out")
    )

    response = await client.get("/search?q=bitcoin&source=coingecko", headers=auth_headers)

    assert response.status_code == 503


@respx.mock
async def test_search_coingecko_drops_coins_without_price(client, auth_headers):
    """Coins absent from the price response should be silently dropped."""
    respx.get("https://api.coingecko.com/api/v3/search").mock(
        return_value=httpx.Response(200, json=COINGECKO_SEARCH_RESPONSE)
    )
    # Only bitcoin has a price; bitcoin-cash is missing from the response
    respx.get("https://api.coingecko.com/api/v3/simple/price").mock(
        return_value=httpx.Response(200, json={"bitcoin": {"usd": 45000.0}})
    )

    response = await client.get("/search?q=bitcoin&source=coingecko", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["external_id"] == "bitcoin"


async def test_search_invalid_source_returns_422(client, auth_headers):
    response = await client.get("/search?q=test&source=unknown", headers=auth_headers)
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Integration tests — POST /products with source=coingecko
# ---------------------------------------------------------------------------


@respx.mock
async def test_register_coingecko_product_creates_documents(client, auth_headers):
    """Registering a coin should create Product, Subscription, and PriceHistory."""
    respx.get("https://api.coingecko.com/api/v3/simple/price").mock(
        return_value=httpx.Response(200, json={"bitcoin": {"usd": 45000.0}})
    )
    respx.get("https://api.coingecko.com/api/v3/coins/bitcoin").mock(
        return_value=httpx.Response(200, json=COINGECKO_COIN_RESPONSE)
    )

    response = await client.post(
        "/products",
        json={"external_id": "bitcoin", "source": "coingecko"},
        headers=auth_headers,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["external_id"] == "bitcoin"
    assert data["source"] == "coingecko"
    assert data["current_price"] == 45000.0
    assert data["currency"] == "USD"
    assert await Product.find().count() == 1
    assert await Subscription.find().count() == 1
    assert await PriceHistory.find().count() == 1


@respx.mock
async def test_register_coingecko_invalid_coin_returns_404(client, auth_headers):
    """An unknown coin slug should return 404."""
    respx.get("https://api.coingecko.com/api/v3/simple/price").mock(
        return_value=httpx.Response(200, json={})
    )
    respx.get("https://api.coingecko.com/api/v3/coins/notacoin").mock(
        return_value=httpx.Response(404, json={"error": "coin not found"})
    )

    response = await client.post(
        "/products",
        json={"external_id": "notacoin", "source": "coingecko"},
        headers=auth_headers,
    )

    assert response.status_code == 404


@respx.mock
async def test_register_same_coingecko_product_twice_returns_409(client, auth_headers):
    """Upsert: same coin registered twice by the same user → 409 on second call."""
    respx.get("https://api.coingecko.com/api/v3/simple/price").mock(
        return_value=httpx.Response(200, json={"bitcoin": {"usd": 45000.0}})
    )
    respx.get("https://api.coingecko.com/api/v3/coins/bitcoin").mock(
        return_value=httpx.Response(200, json=COINGECKO_COIN_RESPONSE)
    )

    await client.post(
        "/products",
        json={"external_id": "bitcoin", "source": "coingecko"},
        headers=auth_headers,
    )
    response = await client.post(
        "/products",
        json={"external_id": "bitcoin", "source": "coingecko"},
        headers=auth_headers,
    )

    assert response.status_code == 409
    assert await Product.find().count() == 1


# ---------------------------------------------------------------------------
# Integration tests — refresh uses CoinGeckoClient for coingecko products
# ---------------------------------------------------------------------------


@respx.mock
async def test_refresh_coingecko_product_records_new_snapshot(client, auth_headers):
    """Refresh should fetch the latest price and add a new PriceHistory entry."""
    respx.get("https://api.coingecko.com/api/v3/simple/price").mock(
        return_value=httpx.Response(200, json={"bitcoin": {"usd": 45000.0}})
    )
    respx.get("https://api.coingecko.com/api/v3/coins/bitcoin").mock(
        return_value=httpx.Response(200, json=COINGECKO_COIN_RESPONSE)
    )
    post_response = await client.post(
        "/products",
        json={"external_id": "bitcoin", "source": "coingecko"},
        headers=auth_headers,
    )
    product_id = post_response.json()["id"]

    # Simulate a price change on refresh
    respx.get("https://api.coingecko.com/api/v3/simple/price").mock(
        return_value=httpx.Response(200, json=BITCOIN_NEW_PRICE)
    )
    respx.get("https://api.coingecko.com/api/v3/coins/bitcoin").mock(
        return_value=httpx.Response(200, json=COINGECKO_COIN_RESPONSE)
    )
    refresh_response = await client.post(
        f"/products/{product_id}/refresh", headers=auth_headers
    )

    assert refresh_response.status_code == 200
    assert refresh_response.json()["current_price"] == 47500.0
    # Original snapshot + refresh snapshot = 2 entries
    assert await PriceHistory.find().count() == 2


@respx.mock
async def test_refresh_coingecko_records_snapshot_even_when_price_unchanged(client, auth_headers):
    """Refresh always creates a snapshot — it is an audit trail, not a diff."""
    respx.get("https://api.coingecko.com/api/v3/simple/price").mock(
        return_value=httpx.Response(200, json={"bitcoin": {"usd": 45000.0}})
    )
    respx.get("https://api.coingecko.com/api/v3/coins/bitcoin").mock(
        return_value=httpx.Response(200, json=COINGECKO_COIN_RESPONSE)
    )
    post_response = await client.post(
        "/products",
        json={"external_id": "bitcoin", "source": "coingecko"},
        headers=auth_headers,
    )
    product_id = post_response.json()["id"]

    # Same price as the initial registration
    respx.get("https://api.coingecko.com/api/v3/simple/price").mock(
        return_value=httpx.Response(200, json={"bitcoin": {"usd": 45000.0}})
    )
    respx.get("https://api.coingecko.com/api/v3/coins/bitcoin").mock(
        return_value=httpx.Response(200, json=COINGECKO_COIN_RESPONSE)
    )
    refresh_response = await client.post(
        f"/products/{product_id}/refresh", headers=auth_headers
    )

    assert refresh_response.status_code == 200
    assert refresh_response.json()["current_price"] == 45000.0
    assert await PriceHistory.find().count() == 2
