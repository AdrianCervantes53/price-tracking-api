"""
Tests for Finnhub integration — reference implementation.

FinnhubClient is retained in the codebase as a reference for the concurrent-calls
pattern (asyncio.gather for quote + search) and the price-fallback strategy
(previous close when market is closed). It is not exposed in the public API
due to Finnhub ToS restrictions on data redistribution.

These tests verify the client logic directly, bypassing the HTTP router layer,
since source=finnhub is no longer a valid value in the public API Literal.
"""

import httpx
import respx

from app.external_clients.finnhub_client import FinnhubClient

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

AAPL_QUOTE_MARKET_OPEN = {"c": 189.25, "d": 1.5, "dp": 0.8, "h": 191.0, "l": 187.5, "o": 188.0, "pc": 187.75, "t": 1714000000}
AAPL_QUOTE_MARKET_CLOSED = {"c": 0, "d": 0, "dp": 0, "h": 0, "l": 0, "o": 0, "pc": 187.75, "t": 1714000000}
INVALID_QUOTE = {"c": 0, "d": 0, "dp": 0, "h": 0, "l": 0, "o": 0, "pc": 0, "t": 0}
APLE_QUOTE = {"c": 14.50, "d": 0.1, "dp": 0.7, "h": 14.8, "l": 14.3, "o": 14.4, "pc": 14.40, "t": 1714000000}


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
    assert FinnhubClient._resolve_name("UNKNOWN", []) == "UNKNOWN"


# ---------------------------------------------------------------------------
# Client-level tests — FinnhubClient.search()
# ---------------------------------------------------------------------------


@respx.mock
async def test_search_returns_only_common_stocks():
    """Only Common Stock results should be returned; ETPs and bonds are dropped."""
    respx.get("https://finnhub.io/api/v1/search").mock(
        return_value=httpx.Response(200, json=FINNHUB_SEARCH_MIXED_TYPES)
    )
    respx.get("https://finnhub.io/api/v1/quote").mock(
        return_value=httpx.Response(200, json=AAPL_QUOTE_MARKET_OPEN)
    )

    results = await FinnhubClient().search("apple")

    assert len(results) == 1
    assert results[0].external_id == "AAPL"
    assert results[0].source == "finnhub"
    assert results[0].price == 189.25
    assert results[0].currency == "USD"


@respx.mock
async def test_search_returns_multiple_results():
    respx.get("https://finnhub.io/api/v1/search").mock(
        return_value=httpx.Response(200, json=FINNHUB_SEARCH_RESPONSE)
    )
    respx.get("https://finnhub.io/api/v1/quote").mock(
        return_value=httpx.Response(200, json=AAPL_QUOTE_MARKET_OPEN)
    )

    results = await FinnhubClient().search("apple")

    assert len(results) == 2


@respx.mock
async def test_search_returns_empty_list_when_no_results():
    respx.get("https://finnhub.io/api/v1/search").mock(
        return_value=httpx.Response(200, json={"count": 0, "result": []})
    )

    results = await FinnhubClient().search("xyznotfound")

    assert results == []


@respx.mock
async def test_search_uses_previous_close_when_market_closed():
    """Search should show previous close price when market is closed (c == 0)."""
    respx.get("https://finnhub.io/api/v1/search").mock(
        return_value=httpx.Response(200, json=FINNHUB_SEARCH_RESPONSE)
    )
    respx.get("https://finnhub.io/api/v1/quote").mock(
        return_value=httpx.Response(200, json=AAPL_QUOTE_MARKET_CLOSED)
    )

    results = await FinnhubClient().search("apple")

    assert results[0].price == 187.75


# ---------------------------------------------------------------------------
# Client-level tests — FinnhubClient.get_product()
# ---------------------------------------------------------------------------


@respx.mock
async def test_get_product_returns_correct_schema():
    respx.get("https://finnhub.io/api/v1/quote").mock(
        return_value=httpx.Response(200, json=AAPL_QUOTE_MARKET_OPEN)
    )
    respx.get("https://finnhub.io/api/v1/search").mock(
        return_value=httpx.Response(200, json=FINNHUB_SEARCH_RESPONSE)
    )

    result = await FinnhubClient().get_product("AAPL")

    assert result.external_id == "AAPL"
    assert result.source == "finnhub"
    assert result.name == "Apple Inc"
    assert result.price == 189.25
    assert result.currency == "USD"


@respx.mock
async def test_get_product_uses_previous_close_when_market_closed():
    respx.get("https://finnhub.io/api/v1/quote").mock(
        return_value=httpx.Response(200, json=AAPL_QUOTE_MARKET_CLOSED)
    )
    respx.get("https://finnhub.io/api/v1/search").mock(
        return_value=httpx.Response(200, json=FINNHUB_SEARCH_RESPONSE)
    )

    result = await FinnhubClient().get_product("AAPL")

    assert result.price == 187.75


@respx.mock
async def test_get_product_raises_404_for_invalid_symbol():
    """A symbol with no price data (c=0, pc=0) should raise 404."""
    respx.get("https://finnhub.io/api/v1/quote").mock(
        return_value=httpx.Response(200, json=INVALID_QUOTE)
    )
    respx.get("https://finnhub.io/api/v1/search").mock(
        return_value=httpx.Response(200, json={"count": 0, "result": []})
    )

    import pytest
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await FinnhubClient().get_product("FAKESYMBOL")

    assert exc_info.value.status_code == 404
