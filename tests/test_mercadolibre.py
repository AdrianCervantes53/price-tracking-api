"""
Tests for MercadoLibre integration:
  - Unit tests for with_retry behavior
  - Unit tests for MercadoLibreClient._to_schema adapter
  - Integration tests for GET /search?source=mercadolibre
  - Integration tests for POST /products with source=mercadolibre
  - Integration tests for refresh on a ML product
"""

import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from app.external_clients.mercadolibre_client import MercadoLibreClient
from app.external_clients.retry import with_retry
from app.models.price_history import PriceHistory
from app.models.product import Product
from app.models.subscription import Subscription

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ML_ITEM_1 = {
    "id": "MLM123456",
    "title": "Mochila Fjallraven Kanken",
    "price": 1299.0,
    "currency_id": "MXN",
    "available_quantity": 5,
    "condition": "new",
    "thumbnail": "https://http2.mlstatic.com/img.jpg",
}

ML_ITEM_2 = {
    "id": "MLM789012",
    "title": "Playera Slim Fit",
    "price": 349.0,
    "currency_id": "MXN",
    "available_quantity": 0,
    "condition": "new",
    "thumbnail": "https://http2.mlstatic.com/img2.jpg",
}

ML_ITEM_1_NEW_PRICE = {**ML_ITEM_1, "price": 999.0}

ML_SEARCH_RESPONSE = {"results": [ML_ITEM_1, ML_ITEM_2]}


@pytest.fixture
async def auth_headers(client):
    await client.post(
        "/auth/register",
        json={"email": "ml@example.com", "password": "securepassword"},
    )
    response = await client.post(
        "/auth/login",
        json={"email": "ml@example.com", "password": "securepassword"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Unit tests — with_retry
# ---------------------------------------------------------------------------


async def test_retry_returns_immediately_on_success():
    call_count = 0

    async def mock_request():
        nonlocal call_count
        call_count += 1
        return httpx.Response(200)

    response = await with_retry(mock_request, max_retries=3, base_delay=0)
    assert response.status_code == 200
    assert call_count == 1


async def test_retry_retries_on_5xx_and_eventually_succeeds():
    responses = [httpx.Response(500), httpx.Response(500), httpx.Response(200)]
    call_count = 0

    async def mock_request():
        nonlocal call_count
        r = responses[call_count]
        call_count += 1
        return r

    with patch("asyncio.sleep", new_callable=AsyncMock):
        response = await with_retry(mock_request, max_retries=3, base_delay=1.0)

    assert response.status_code == 200
    assert call_count == 3


async def test_retry_returns_last_response_after_exhausting_retries():
    async def mock_request():
        return httpx.Response(500)

    with patch("asyncio.sleep", new_callable=AsyncMock):
        response = await with_retry(mock_request, max_retries=2, base_delay=1.0)

    assert response.status_code == 500


async def test_retry_raises_timeout_after_exhausting_retries():
    async def mock_request():
        raise httpx.TimeoutException("timed out")

    with patch("asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(httpx.TimeoutException):
            await with_retry(mock_request, max_retries=2, base_delay=1.0)


async def test_retry_respects_retry_after_header_on_429():
    responses = [
        httpx.Response(429, headers={"Retry-After": "2"}),
        httpx.Response(200),
    ]
    call_count = 0

    async def mock_request():
        nonlocal call_count
        r = responses[call_count]
        call_count += 1
        return r

    sleep_calls = []
    async def fake_sleep(seconds):
        sleep_calls.append(seconds)

    with patch("asyncio.sleep", side_effect=fake_sleep):
        response = await with_retry(mock_request, max_retries=3, base_delay=1.0)

    assert response.status_code == 200
    assert sleep_calls[0] == 2.0  # respected Retry-After


# ---------------------------------------------------------------------------
# Unit tests — MercadoLibreClient adapter
# ---------------------------------------------------------------------------


def test_to_schema_maps_fields_correctly():
    result = MercadoLibreClient._to_schema(ML_ITEM_1)
    assert result.external_id == "MLM123456"
    assert result.source == "mercadolibre"
    assert result.name == "Mochila Fjallraven Kanken"
    assert result.price == 1299.0
    assert result.currency == "MXN"


def test_to_schema_handles_null_price():
    item = {**ML_ITEM_1, "price": None}
    result = MercadoLibreClient._to_schema(item)
    assert result.price == 0.0


# ---------------------------------------------------------------------------
# Integration tests — GET /search?source=mercadolibre
# ---------------------------------------------------------------------------


@respx.mock
async def test_search_ml_returns_results(client, auth_headers):
    respx.get("https://api.mercadolibre.com/sites/MLM/search").mock(
        return_value=httpx.Response(200, json=ML_SEARCH_RESPONSE)
    )
    response = await client.get(
        "/search?q=mochila&source=mercadolibre", headers=auth_headers
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["external_id"] == "MLM123456"
    assert data[0]["source"] == "mercadolibre"
    assert data[0]["currency"] == "MXN"


@respx.mock
async def test_search_ml_empty_results(client, auth_headers):
    respx.get("https://api.mercadolibre.com/sites/MLM/search").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    response = await client.get(
        "/search?q=noresults&source=mercadolibre", headers=auth_headers
    )

    assert response.status_code == 200
    assert response.json() == []


@respx.mock
async def test_search_ml_timeout_returns_503(client, auth_headers):
    respx.get("https://api.mercadolibre.com/sites/MLM/search").mock(
        side_effect=httpx.TimeoutException("timed out")
    )
    response = await client.get(
        "/search?q=mochila&source=mercadolibre", headers=auth_headers
    )
    assert response.status_code == 503


async def test_search_invalid_source_returns_422(client, auth_headers):
    response = await client.get(
        "/search?q=test&source=unknown", headers=auth_headers
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Integration tests — POST /products with source=mercadolibre
# ---------------------------------------------------------------------------


@respx.mock
async def test_register_ml_product_creates_documents(client, auth_headers):
    respx.get("https://api.mercadolibre.com/items/MLM123456").mock(
        return_value=httpx.Response(200, json=ML_ITEM_1)
    )
    response = await client.post(
        "/products",
        json={"external_id": "MLM123456", "source": "mercadolibre"},
        headers=auth_headers,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["external_id"] == "MLM123456"
    assert data["source"] == "mercadolibre"
    assert data["current_price"] == 1299.0
    assert data["currency"] == "MXN"
    assert await Product.find().count() == 1
    assert await Subscription.find().count() == 1
    assert await PriceHistory.find().count() == 1


@respx.mock
async def test_register_ml_product_not_found_returns_404(client, auth_headers):
    respx.get("https://api.mercadolibre.com/items/MLM999999").mock(
        return_value=httpx.Response(404)
    )
    response = await client.post(
        "/products",
        json={"external_id": "MLM999999", "source": "mercadolibre"},
        headers=auth_headers,
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Integration tests — refresh uses correct client for ML products
# ---------------------------------------------------------------------------


@respx.mock
async def test_refresh_ml_product_uses_ml_client(client, auth_headers):
    respx.get("https://api.mercadolibre.com/items/MLM123456").mock(
        return_value=httpx.Response(200, json=ML_ITEM_1)
    )
    post_response = await client.post(
        "/products",
        json={"external_id": "MLM123456", "source": "mercadolibre"},
        headers=auth_headers,
    )
    product_id = post_response.json()["id"]

    respx.get("https://api.mercadolibre.com/items/MLM123456").mock(
        return_value=httpx.Response(200, json=ML_ITEM_1_NEW_PRICE)
    )
    refresh_response = await client.post(
        f"/products/{product_id}/refresh", headers=auth_headers
    )

    assert refresh_response.status_code == 200
    assert refresh_response.json()["current_price"] == 999.0
    assert await PriceHistory.find().count() == 2
