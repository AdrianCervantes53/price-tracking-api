"""
Tests for Finnhub integration:
  - Unit tests for FinnhubClient._to_schema adapter
  - Unit tests for FinnhubClient._resolve_name
  - Integration tests for GET /search?source=finnhub
  - Integration tests for POST /products with source=finnhub
  - Integration tests for refresh on a Finnhub product
"""

import httpx
import pytest
import respx

from app.external_clients.finnhub_client import FinnhubClient
from app.models.price_history import PriceHistory
from app.models.product import Product
from app.models.subscription import Subscription

# ---------------------------------------------------------------------------
# Fixtures — realistic Finnhub payloads
# ---------------------------------------------------------------------------

FINNHUB_SEARCH_RESPONSE = {
    "count": 2,
    "result": [
        {
            "description": "Apple Inc",
            "displaySymbol": "AAPL",
            "symbol": "AAPL",
            "type": "Common Stock",
        },
        {
            "description": "Apple Hospitality REIT Inc",
            "displaySymbol": "APLE",
            "symbol": "APLE",
            "type": "Common Stock",
        },
    ],
}

FINNHUB_SEARCH_MIXED_TYPES = {
    "count": 3,
    "result": [
        {"description": "Apple Inc", "displaySymbol": "AAPL", "symbol": "AAPL", "type": "Common Stock"},
        {"description": "Apple ETF", "displaySymbol": "AAPL-ETF", "symbol": "AAPL-ETF", "type": "ETP"},
        {"description": "Apple Bond", "displaySymbol": "AAPL-B", "symbol": "AAPL-B", "type": "Bond"},
    ],
}

# Market open: c > 0
AAPL_QUOTE_MARKET_OPEN = {"c": 189.25, "d": 1.5, "dp": 0.8, "h": 191.0, "l": 187.5, "o": 188.0, "pc": 187.75, "t": 1714000000}

# Market closed: c == 0, price comes from pc (previous close)
AAPL_QUOTE_MARKET_CLOSED = {"c": 0, "d": 0, "dp": 0, "h": 0, "l": 0, "o": 0, "pc": 187.75, "t": 1714000000}

# Invalid symbol: c and pc both 0
INVALID_QUOTE = {"c": 0, "d": 0, "dp": 0, "h": 0, "l": 0, "o": 0, "pc": 0, "t": 0}

APLE_QUOTE = {"c": 14.50, "d": 0.1, "dp": 0.7, "h": 14.8, "l": 14.3, "o": 14.4, "pc": 14.40, "t": 1714000000}

AAPL_NEW_PRICE_QUOTE = {**AAPL_QUOTE_MARKET_OPEN, "c": 195.00}


@pytest.fixture
async def auth_headers(client):
    await client.post(
        "/auth/register",
        json={"email": "finnhub@example.com", "password": "securepassword"},
    )
    response = await client.post(
        "/auth/login",
        json={"email": "finnhub@example.com", "password": "securepassword"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Unit tests — _to_schema adapter
# ---------------------------------------------------------------------------


def test_to_schema_uses_current_price_when_market_open():
    """When c > 0 the market is open — use real-time price."""
    stock = {"symbol": "AAPL", "description": "Apple Inc"}
    result = FinnhubClient._to_schema(stock, AAPL_QUOTE_MARKET_OPEN)

    assert result.external_id == "AAPL"
    assert result.source == "finnhub"
    assert result.name == "Apple Inc"
    assert result.price == 189.25
    assert result.currency == "USD"


def test_to_schema_falls_back_to_previous_close_when_market_closed():
    """When c == 0 the market is closed — use previous close (pc) instead."""
    stock = {"symbol": "AAPL", "description": "Apple Inc"}
    result = FinnhubClient._to_schema(stock, AAPL_QUOTE_MARKET_CLOSED)

    assert result.price == 187.75


def test_to_schema_uses_symbol_as_name_when_description_missing():
    """Description may be absent for some non-US tickers."""
    stock = {"symbol": "XYZ"}
    result = FinnhubClient._to_schema(stock, AAPL_QUOTE_MARKET_OPEN)

    assert result.name == "XYZ"


def test_to_schema_currency_is_always_usd():
    stock = {"symbol": "AAPL", "description": "Apple Inc"}
    result = FinnhubClient._to_schema(stock, AAPL_QUOTE_MARKET_OPEN)

    assert result.currency == "USD"


# ---------------------------------------------------------------------------
# Unit tests — _resolve_name
# ---------------------------------------------------------------------------


def test_resolve_name_returns_description_for_exact_symbol_match():
    results = FINNHUB_SEARCH_RESPONSE["result"]
    assert FinnhubClient._resolve_name("AAPL", results) == "Apple Inc"
    assert FinnhubClient._resolve_name("APLE", results) == "Apple Hospitality REIT Inc"


def test_resolve_name_falls_back_to_symbol_when_no_match():
    """Handles symbols not found in search results (e.g. obscure tickers)."""
    assert FinnhubClient._resolve_name("UNKNOWN", []) == "UNKNOWN"


# ---------------------------------------------------------------------------
# Integration tests — GET /search?source=finnhub
# ---------------------------------------------------------------------------


@respx.mock
async def test_search_finnhub_returns_filtered_results(client, auth_headers):
    """Only Common Stock results should be returned; ETPs and bonds are dropped."""
    respx.get("https://finnhub.io/api/v1/search").mock(
        return_value=httpx.Response(200, json=FINNHUB_SEARCH_MIXED_TYPES)
    )
    # One quote call per Common Stock result (only AAPL passes the filter)
    respx.get("https://finnhub.io/api/v1/quote").mock(
        return_value=httpx.Response(200, json=AAPL_QUOTE_MARKET_OPEN)
    )

    response = await client.get("/search?q=apple&source=finnhub", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["external_id"] == "AAPL"
    assert data[0]["source"] == "finnhub"
    assert data[0]["price"] == 189.25
    assert data[0]["currency"] == "USD"


@respx.mock
async def test_search_finnhub_returns_multiple_results(client, auth_headers):
    respx.get("https://finnhub.io/api/v1/search").mock(
        return_value=httpx.Response(200, json=FINNHUB_SEARCH_RESPONSE)
    )
    # gather will call /quote twice (once per symbol); mock returns same response for both
    respx.get("https://finnhub.io/api/v1/quote").mock(
        return_value=httpx.Response(200, json=AAPL_QUOTE_MARKET_OPEN)
    )

    response = await client.get("/search?q=apple&source=finnhub", headers=auth_headers)

    assert response.status_code == 200
    assert len(response.json()) == 2


@respx.mock
async def test_search_finnhub_empty_results(client, auth_headers):
    respx.get("https://finnhub.io/api/v1/search").mock(
        return_value=httpx.Response(200, json={"count": 0, "result": []})
    )

    response = await client.get("/search?q=xyznotfound&source=finnhub", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == []


@respx.mock
async def test_search_finnhub_timeout_returns_503(client, auth_headers):
    respx.get("https://finnhub.io/api/v1/search").mock(
        side_effect=httpx.TimeoutException("timed out")
    )

    response = await client.get("/search?q=apple&source=finnhub", headers=auth_headers)

    assert response.status_code == 503


@respx.mock
async def test_search_finnhub_price_uses_previous_close_when_market_closed(client, auth_headers):
    """When the market is closed, search results should show previous close price."""
    respx.get("https://finnhub.io/api/v1/search").mock(
        return_value=httpx.Response(200, json=FINNHUB_SEARCH_RESPONSE)
    )
    respx.get("https://finnhub.io/api/v1/quote").mock(
        return_value=httpx.Response(200, json=AAPL_QUOTE_MARKET_CLOSED)
    )

    response = await client.get("/search?q=apple&source=finnhub", headers=auth_headers)

    assert response.status_code == 200
    # Price should be the previous close (pc), not 0
    assert response.json()[0]["price"] == 187.75


async def test_search_invalid_source_returns_422(client, auth_headers):
    response = await client.get("/search?q=test&source=unknown", headers=auth_headers)
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Integration tests — POST /products with source=finnhub
# ---------------------------------------------------------------------------


@respx.mock
async def test_register_finnhub_product_creates_documents(client, auth_headers):
    """Registering a stock should create Product, Subscription, and PriceHistory."""
    # get_product makes two concurrent calls: /quote and /search
    respx.get("https://finnhub.io/api/v1/quote").mock(
        return_value=httpx.Response(200, json=AAPL_QUOTE_MARKET_OPEN)
    )
    respx.get("https://finnhub.io/api/v1/search").mock(
        return_value=httpx.Response(200, json=FINNHUB_SEARCH_RESPONSE)
    )

    response = await client.post(
        "/products",
        json={"external_id": "AAPL", "source": "finnhub"},
        headers=auth_headers,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["external_id"] == "AAPL"
    assert data["source"] == "finnhub"
    assert data["current_price"] == 189.25
    assert data["currency"] == "USD"
    assert await Product.find().count() == 1
    assert await Subscription.find().count() == 1
    assert await PriceHistory.find().count() == 1


@respx.mock
async def test_register_finnhub_product_invalid_symbol_returns_404(client, auth_headers):
    """A symbol with no price data (c=0, pc=0) should return 404."""
    respx.get("https://finnhub.io/api/v1/quote").mock(
        return_value=httpx.Response(200, json=INVALID_QUOTE)
    )
    respx.get("https://finnhub.io/api/v1/search").mock(
        return_value=httpx.Response(200, json={"count": 0, "result": []})
    )

    response = await client.post(
        "/products",
        json={"external_id": "FAKESYMBOL", "source": "finnhub"},
        headers=auth_headers,
    )

    assert response.status_code == 404


@respx.mock
async def test_register_same_finnhub_product_twice_creates_one_product(client, auth_headers):
    """Upsert logic: registering the same ticker twice creates one Product, two Subscriptions
    only if from different users — here it should create one of each (idempotent for same user)."""
    respx.get("https://finnhub.io/api/v1/quote").mock(
        return_value=httpx.Response(200, json=AAPL_QUOTE_MARKET_OPEN)
    )
    respx.get("https://finnhub.io/api/v1/search").mock(
        return_value=httpx.Response(200, json=FINNHUB_SEARCH_RESPONSE)
    )

    await client.post(
        "/products",
        json={"external_id": "AAPL", "source": "finnhub"},
        headers=auth_headers,
    )
    response = await client.post(
        "/products",
        json={"external_id": "AAPL", "source": "finnhub"},
        headers=auth_headers,
    )

    # Second registration should be rejected (already subscribed)
    assert response.status_code == 409
    assert await Product.find().count() == 1


# ---------------------------------------------------------------------------
# Integration tests — refresh uses FinnhubClient for finnhub products
# ---------------------------------------------------------------------------


@respx.mock
async def test_refresh_finnhub_product_records_new_snapshot(client, auth_headers):
    """Refresh should fetch the latest price and add a new PriceHistory entry."""
    respx.get("https://finnhub.io/api/v1/quote").mock(
        return_value=httpx.Response(200, json=AAPL_QUOTE_MARKET_OPEN)
    )
    respx.get("https://finnhub.io/api/v1/search").mock(
        return_value=httpx.Response(200, json=FINNHUB_SEARCH_RESPONSE)
    )
    post_response = await client.post(
        "/products",
        json={"external_id": "AAPL", "source": "finnhub"},
        headers=auth_headers,
    )
    product_id = post_response.json()["id"]

    # Simulate a price change on the second call
    respx.get("https://finnhub.io/api/v1/quote").mock(
        return_value=httpx.Response(200, json=AAPL_NEW_PRICE_QUOTE)
    )
    respx.get("https://finnhub.io/api/v1/search").mock(
        return_value=httpx.Response(200, json=FINNHUB_SEARCH_RESPONSE)
    )
    refresh_response = await client.post(
        f"/products/{product_id}/refresh", headers=auth_headers
    )

    assert refresh_response.status_code == 200
    assert refresh_response.json()["current_price"] == 195.00
    # Original snapshot + refresh snapshot = 2 entries
    assert await PriceHistory.find().count() == 2


@respx.mock
async def test_refresh_finnhub_market_closed_uses_previous_close(client, auth_headers):
    """Even when the market is closed, refresh should record the previous close price."""
    respx.get("https://finnhub.io/api/v1/quote").mock(
        return_value=httpx.Response(200, json=AAPL_QUOTE_MARKET_OPEN)
    )
    respx.get("https://finnhub.io/api/v1/search").mock(
        return_value=httpx.Response(200, json=FINNHUB_SEARCH_RESPONSE)
    )
    post_response = await client.post(
        "/products",
        json={"external_id": "AAPL", "source": "finnhub"},
        headers=auth_headers,
    )
    product_id = post_response.json()["id"]

    respx.get("https://finnhub.io/api/v1/quote").mock(
        return_value=httpx.Response(200, json=AAPL_QUOTE_MARKET_CLOSED)
    )
    respx.get("https://finnhub.io/api/v1/search").mock(
        return_value=httpx.Response(200, json=FINNHUB_SEARCH_RESPONSE)
    )
    refresh_response = await client.post(
        f"/products/{product_id}/refresh", headers=auth_headers
    )

    assert refresh_response.status_code == 200
    assert refresh_response.json()["current_price"] == 187.75
    assert await PriceHistory.find().count() == 2
