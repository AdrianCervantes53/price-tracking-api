import httpx
from fastapi import HTTPException, status

from app.schemas.search import ExternalProductResult

_BASE_URL = "https://fakestoreapi.com"
_TIMEOUT = 10.0


class FakeStoreClient:
    async def search(self, q: str) -> list[ExternalProductResult]:
        """
        Fetches all products from FakeStore and filters by title.
        FakeStore has no native search endpoint.
        """
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.get(f"{_BASE_URL}/products")
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="External API timed out",
            )

        if response.status_code >= 500:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="External API returned an error",
            )

        products = response.json()
        matches = [p for p in products if q.lower() in p["title"].lower()]
        return [self._to_schema(p) for p in matches]

    async def get_product(self, external_id: str) -> ExternalProductResult:
        """Fetches a single product by its external ID."""
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.get(f"{_BASE_URL}/products/{external_id}")
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="External API timed out",
            )

        if response.status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product '{external_id}' not found in external API",
            )
        if response.status_code >= 500:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="External API returned an error",
            )

        return self._to_schema(response.json())

    @staticmethod
    def _to_schema(data: dict) -> ExternalProductResult:
        return ExternalProductResult(
            external_id=str(data["id"]),
            source="fakestore",
            name=data["title"],
            price=data["price"],
            currency="USD",
        )
