import asyncio

import httpx
from fastapi import HTTPException, status

from app.core.config import settings
from app.external_clients.retry import with_retry
from app.schemas.search import ExternalProductResult

_BASE_URL = "https://api.coingecko.com/api/v3"
_TIMEOUT = 10.0
_SEARCH_LIMIT = 5  # caps the number of coins returned from search


class CoinGeckoClient:
    def __init__(self) -> None:
        self._api_key = settings.coingecko_api_key

    def _headers(self) -> dict:
        """
        Returns auth headers for the CoinGecko Demo API.

        The API works without a key but rate limit is dynamic (5–15 req/min).
        With a free Demo key, the rate limit is stable at 30 req/min.
        """
        if self._api_key:
            return {"x-cg-demo-api-key": self._api_key}
        return {}

    # ------------------------------------------------------------------
    # Public interface (matches factory contract)
    # ------------------------------------------------------------------

    async def search(self, q: str) -> list[ExternalProductResult]:
        """
        Searches CoinGecko for coins matching the query term.

        Two-stage process:
          1. GET /search        — returns matching coins with ids and names
          2. GET /simple/price  — fetches current USD price for all results
                                  in a single batched call (no N concurrent calls needed)

        Results are filtered to the coins array only; exchanges and NFTs are excluded.
        Coins with no price data in the price response are silently dropped.
        """
        try:
            async with httpx.AsyncClient(
                timeout=_TIMEOUT, headers=self._headers()
            ) as client:
                search_response = await with_retry(
                    lambda: client.get(f"{_BASE_URL}/search", params={"query": q})
                )

                if search_response.status_code >= 500:
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail="External API returned an error",
                    )

                coins = search_response.json().get("coins", [])[:_SEARCH_LIMIT]

                if not coins:
                    return []

                # CoinGecko accepts a comma-joined list of ids — one call replaces N
                ids = ",".join(c["id"] for c in coins)
                prices_response = await with_retry(
                    lambda: client.get(
                        f"{_BASE_URL}/simple/price",
                        params={"ids": ids, "vs_currencies": "usd"},
                    )
                )

        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="External API timed out",
            )

        prices = prices_response.json()

        results: list[ExternalProductResult] = []
        for coin in coins:
            price = prices.get(coin["id"], {}).get("usd")
            if price is None:
                # Skip coins not present in the price response
                continue
            results.append(self._to_schema(coin["id"], coin["name"], price))

        return results

    async def get_product(self, external_id: str) -> ExternalProductResult:
        """
        Fetches the current price and name for a coin by its CoinGecko slug.

        Makes two concurrent calls to minimise latency:
          - GET /simple/price  → current USD price
          - GET /coins/{id}    → coin name and metadata

        Raises 404 when the coin id is not recognised by CoinGecko or
        when no price data is available for the given id.
        """
        try:
            async with httpx.AsyncClient(
                timeout=_TIMEOUT, headers=self._headers()
            ) as client:
                price_response, coin_response = await asyncio.gather(
                    with_retry(
                        lambda: client.get(
                            f"{_BASE_URL}/simple/price",
                            params={"ids": external_id, "vs_currencies": "usd"},
                        )
                    ),
                    with_retry(
                        lambda: client.get(
                            f"{_BASE_URL}/coins/{external_id}",
                            params={
                                "localization": "false",
                                "tickers": "false",
                                "market_data": "false",
                                "community_data": "false",
                                "developer_data": "false",
                            },
                        )
                    ),
                )
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="External API timed out",
            )

        if coin_response.status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Coin '{external_id}' not found on CoinGecko",
            )

        if coin_response.status_code >= 500 or price_response.status_code >= 500:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="External API returned an error",
            )

        price = price_response.json().get(external_id, {}).get("usd")

        if price is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No price data available for '{external_id}'",
            )

        name = coin_response.json().get("name", external_id)

        return self._to_schema(external_id, name, price)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_schema(coin_id: str, name: str, price: float) -> ExternalProductResult:
        """Maps CoinGecko coin data to the shared ExternalProductResult schema."""
        return ExternalProductResult(
            external_id=coin_id,
            source="coingecko",
            name=name,
            price=price,
            currency="USD",
        )
