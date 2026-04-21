import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient

from app.main import app
from app.models.user import User
from app.models.product import Product
from app.models.subscription import Subscription
from app.models.price_history import PriceHistory


@pytest_asyncio.fixture(autouse=True)
async def init_test_db():
    """Initialize Beanie with an in-memory MongoDB mock before each test."""
    client = AsyncMongoMockClient()
    await init_beanie(
        database=client["test_db"],
        document_models=[User, Product, Subscription, PriceHistory],
    )


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    """Async HTTP client pointed at the FastAPI app."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
