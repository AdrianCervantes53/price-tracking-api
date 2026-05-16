from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.search import ExternalProductResult
from app.services import search_service

router = APIRouter()


@router.get(
    "",
    response_model=list[ExternalProductResult],
    summary="Search assets in external data source (results not persisted)",
)
async def search_products(
    q: str = Query(..., min_length=1, description="Search term"),
    source: Literal["fakestore", "coingecko"] = Query(
        "fakestore",
        description="Data source to search (fakestore | coingecko)",
    ),
    current_user: User = Depends(get_current_user),
):
    return await search_service.search_products(q, source)
