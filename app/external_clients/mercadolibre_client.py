import httpx
from fastapi import HTTPException, status

from app.core.config import settings
from app.external_clients.retry import with_retry
from app.schemas.search import ExternalProductResult

_BASE_URL = "https://api.mercadolibre.com"
_TIMEOUT = 10.0


class MercadoLibreClient:
    async def search(self, q: str) -> list[ExternalProductResult]:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await with_retry(
                lambda: client.get(
                    f"{_BASE_URL}/sites/{settings.ml_site_id}/search",
                    params={"q": q, "limit": 10},
                )
            )

        if response.status_code >= 500:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="External API returned an error",
            )

        return [self._to_schema(item) for item in response.json().get("results", [])]

    async def get_product(self, external_id: str) -> ExternalProductResult:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await with_retry(
                lambda: client.get(f"{_BASE_URL}/items/{external_id}")
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
            source="mercadolibre",
            name=data["title"],
            price=data.get("price") or 0.0,
            currency=data.get("currency_id", "MXN"),
        )
