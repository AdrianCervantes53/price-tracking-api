import asyncio

import httpx
from fastapi import HTTPException, status

from app.core.config import settings
from app.external_clients.retry import with_retry
from app.schemas.search import ExternalProductResult

_BASE_URL = "https://finnhub.io/api/v1"
_TIMEOUT = 10.0
_SEARCH_LIMIT = 5  # caps concurrent /quote calls made during search


class FinnhubClient:
    def __init__(self) -> None:
        self._api_key = settings.finnhub_api_key

    # ------------------------------------------------------------------
    # Public interface (matches factory contract)
    # ------------------------------------------------------------------

    async def search(self, q: str) -> list[ExternalProductResult]:
        """
        Searches Finnhub for stocks matching the query term.

        Two-stage process:
          1. GET /search  — returns matching symbols + company names
          2. GET /quote   — fetches current price for each symbol (concurrent)

        Results are filtered to Common Stock to exclude ETFs, bonds, etc.
        Quote calls run concurrently via asyncio.gather; failed quotes are
        silently dropped so one bad symbol doesn't block the whole response.
        """
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                search_response = await with_retry(
                    lambda: client.get(
                        f"{_BASE_URL}/search",
                        params={"q": q, "token": self._api_key},
                    )
                )

                if search_response.status_code >= 500:
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail="External API returned an error",
                    )

                raw = search_response.json().get("result", [])
                # Keep only common stocks; cap at _SEARCH_LIMIT to bound concurrent calls
                stocks = [r for r in raw if r.get("type") == "Common Stock"][:_SEARCH_LIMIT]

                if not stocks:
                    return []

                # Fetch price for each symbol concurrently.
                # return_exceptions=True lets us skip individual failures gracefully.
                quotes = await asyncio.gather(
                    *[
                        with_retry(
                            # Default arg (s=stock) freezes the loop variable in the closure
                            lambda s=stock: client.get(
                                f"{_BASE_URL}/quote",
                                params={"symbol": s["symbol"], "token": self._api_key},
                            )
                        )
                        for stock in stocks
                    ],
                    return_exceptions=True,
                )

        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="External API timed out",
            )

        results: list[ExternalProductResult] = []
        for stock, quote in zip(stocks, quotes):
            # Skip symbols where the quote request failed
            if isinstance(quote, Exception):
                continue
            results.append(self._to_schema(stock, quote.json()))

        return results

    async def get_product(self, external_id: str) -> ExternalProductResult:
        """
        Fetches the current price and company name for a stock symbol.

        Makes two concurrent calls to minimise latency:
          - GET /quote  → price data (current or previous close)
          - GET /search → company description (used as the product name)

        Raises 404 when both current price (c) and previous close (pc) are 0,
        which indicates an invalid or untraded symbol.
        """
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                quote_response, search_response = await asyncio.gather(
                    with_retry(
                        lambda: client.get(
                            f"{_BASE_URL}/quote",
                            params={"symbol": external_id, "token": self._api_key},
                        )
                    ),
                    with_retry(
                        lambda: client.get(
                            f"{_BASE_URL}/search",
                            params={"q": external_id, "token": self._api_key},
                        )
                    ),
                )
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="External API timed out",
            )

        if quote_response.status_code >= 500:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="External API returned an error",
            )

        quote = quote_response.json()

        # Finnhub returns c=0 and pc=0 for unknown symbols — treat as not found
        if quote.get("c", 0) == 0 and quote.get("pc", 0) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Symbol '{external_id}' not found or has no price data",
            )

        search_results = search_response.json().get("result", [])
        name = self._resolve_name(external_id, search_results)

        return self._to_schema({"symbol": external_id, "description": name}, quote)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_name(symbol: str, search_results: list[dict]) -> str:
        """
        Returns the company description for an exact symbol match.
        Falls back to the symbol itself when no match is found
        (e.g. non-US exchanges with unusual ticker formats).
        """
        for result in search_results:
            if result.get("symbol") == symbol:
                return result.get("description", symbol)
        return symbol

    @staticmethod
    def _to_schema(stock: dict, quote: dict) -> ExternalProductResult:
        """
        Maps Finnhub stock + quote data to the shared ExternalProductResult.

        Price logic:
          - c  (current)        > 0 → market is open, use real-time price
          - c == 0, pc > 0      → market is closed, use previous close
          - c == 0, pc == 0     → invalid symbol (caught upstream in get_product)

        All Finnhub stock prices are denominated in USD.
        """
        price = quote.get("c") or quote.get("pc", 0.0)
        return ExternalProductResult(
            external_id=stock["symbol"],
            source="finnhub",
            name=stock.get("description", stock["symbol"]),
            price=price,
            currency="USD",
        )
