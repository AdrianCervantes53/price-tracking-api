"""
Tests for MercadoLibre integration — reference implementation.

MercadoLibreClient is retained in the codebase as a reference for the retry +
adapter pattern. It is not exposed in the public API because ML restricted
public access to their search and item endpoints in 2024–2025 (403 Forbidden).

These tests verify the client logic directly, bypassing the HTTP router layer,
since source=mercadolibre is no longer a valid value in the public API Literal.
"""

from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from app.external_clients.mercadolibre_client import MercadoLibreClient
from app.external_clients.retry import with_retry

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

ML_SEARCH_RESPONSE = {"results": [ML_ITEM_1, ML_ITEM_2]}


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
# Unit tests — MercadoLibreClient._to_schema adapter
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
# Client-level tests — MercadoLibreClient.search()
# ---------------------------------------------------------------------------


@respx.mock
async def test_search_returns_results():
    respx.get("https://api.mercadolibre.com/sites/MLM/search").mock(
        return_value=httpx.Response(200, json=ML_SEARCH_RESPONSE)
    )

    results = await MercadoLibreClient().search("mochila")

    assert len(results) == 2
    assert results[0].external_id == "MLM123456"
    assert results[0].source == "mercadolibre"
    assert results[0].currency == "MXN"


@respx.mock
async def test_search_returns_empty_list_when_no_results():
    respx.get("https://api.mercadolibre.com/sites/MLM/search").mock(
        return_value=httpx.Response(200, json={"results": []})
    )

    results = await MercadoLibreClient().search("noresults")

    assert results == []


@respx.mock
async def test_search_raises_503_on_timeout():
    respx.get("https://api.mercadolibre.com/sites/MLM/search").mock(
        side_effect=httpx.TimeoutException("timed out")
    )

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await MercadoLibreClient().search("mochila")

    assert exc_info.value.status_code == 503


# ---------------------------------------------------------------------------
# Client-level tests — MercadoLibreClient.get_product()
# ---------------------------------------------------------------------------


@respx.mock
async def test_get_product_returns_correct_schema():
    respx.get("https://api.mercadolibre.com/items/MLM123456").mock(
        return_value=httpx.Response(200, json=ML_ITEM_1)
    )

    result = await MercadoLibreClient().get_product("MLM123456")

    assert result.external_id == "MLM123456"
    assert result.source == "mercadolibre"
    assert result.name == "Mochila Fjallraven Kanken"
    assert result.price == 1299.0
    assert result.currency == "MXN"


@respx.mock
async def test_get_product_raises_404_when_not_found():
    respx.get("https://api.mercadolibre.com/items/MLM999999").mock(
        return_value=httpx.Response(404)
    )

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await MercadoLibreClient().get_product("MLM999999")

    assert exc_info.value.status_code == 404
