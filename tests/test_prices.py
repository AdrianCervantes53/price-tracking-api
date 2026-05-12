from datetime import datetime, timezone, timedelta

import httpx
import pytest
import respx

from app.models.price_history import PriceHistory
from app.models.product import Product
from app.models.subscription import Subscription

FAKESTORE_PRODUCT_1 = {
    "id": 1,
    "title": "Fjallraven Backpack",
    "price": 109.95,
    "category": "men's clothing",
    "description": "Your perfect pack",
    "image": "https://fakestoreapi.com/img/1.jpg",
    "rating": {"rate": 3.9, "count": 120},
}

FAKESTORE_PRODUCT_1_NEW_PRICE = {**FAKESTORE_PRODUCT_1, "price": 89.99}


@pytest.fixture
async def auth_headers(client):
    await client.post(
        "/auth/register",
        json={"email": "prices@example.com", "password": "securepassword"},
    )
    response = await client.post(
        "/auth/login",
        json={"email": "prices@example.com", "password": "securepassword"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def auth_headers_user2(client):
    await client.post(
        "/auth/register",
        json={"email": "prices2@example.com", "password": "securepassword"},
    )
    response = await client.post(
        "/auth/login",
        json={"email": "prices2@example.com", "password": "securepassword"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
@respx.mock
async def subscribed_product(client, auth_headers):
    """Registers product 1 for the primary test user. Returns the product_id."""
    respx.get("https://fakestoreapi.com/products/1").mock(
        return_value=httpx.Response(200, json=FAKESTORE_PRODUCT_1)
    )
    response = await client.post(
        "/products",
        json={"external_id": "1", "source": "fakestore"},
        headers=auth_headers,
    )
    return response.json()["id"]


# ---------------------------------------------------------------------------
# GET /products/{id}
# ---------------------------------------------------------------------------


async def test_get_product_returns_detail_when_subscribed(
    client, auth_headers, subscribed_product
):
    response = await client.get(
        f"/products/{subscribed_product}", headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == subscribed_product
    assert data["external_id"] == "1"
    assert data["name"] == "Fjallraven Backpack"
    assert data["current_price"] == 109.95


async def test_get_product_returns_404_when_not_subscribed(
    client, auth_headers_user2, subscribed_product
):
    """A user without a subscription cannot see the product detail."""
    response = await client.get(
        f"/products/{subscribed_product}", headers=auth_headers_user2
    )
    assert response.status_code == 404


async def test_get_product_returns_404_for_invalid_id(client, auth_headers):
    response = await client.get("/products/not-a-valid-id", headers=auth_headers)
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /products/{id}/history
# ---------------------------------------------------------------------------


async def test_get_history_returns_entries_ordered_by_date_desc(
    client, auth_headers, subscribed_product
):
    """Inserts snapshots with explicit timestamps and verifies desc ordering."""
    now = datetime.now(timezone.utc)
    product = await Product.get(subscribed_product)
    product_id = str(product.id)

    older = PriceHistory(product_id=product_id, price=120.00, timestamp=now - timedelta(days=2))
    newer = PriceHistory(product_id=product_id, price=100.00, timestamp=now - timedelta(days=1))
    await older.insert()
    await newer.insert()

    response = await client.get(
        f"/products/{subscribed_product}/history", headers=auth_headers
    )
    assert response.status_code == 200
    entries = response.json()
    # At least the initial snapshot + the two we inserted
    assert len(entries) >= 3
    # Timestamps must be in descending order
    timestamps = [e["timestamp"] for e in entries]
    assert timestamps == sorted(timestamps, reverse=True)


async def test_get_history_returns_404_when_not_subscribed(
    client, auth_headers_user2, subscribed_product
):
    response = await client.get(
        f"/products/{subscribed_product}/history", headers=auth_headers_user2
    )
    assert response.status_code == 404


async def test_get_history_returns_404_for_invalid_id(client, auth_headers):
    response = await client.get("/products/not-a-valid-id/history", headers=auth_headers)
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /products/{id}/refresh
# ---------------------------------------------------------------------------


@respx.mock
async def test_refresh_updates_price_and_creates_snapshot(
    client, auth_headers, subscribed_product
):
    """Refresh with a new price updates the product and adds a PriceHistory entry."""
    respx.get("https://fakestoreapi.com/products/1").mock(
        return_value=httpx.Response(200, json=FAKESTORE_PRODUCT_1_NEW_PRICE)
    )
    history_before = await PriceHistory.find().count()

    response = await client.post(
        f"/products/{subscribed_product}/refresh", headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["current_price"] == 89.99
    assert data["id"] == subscribed_product

    product = await Product.get(subscribed_product)
    assert product.current_price == 89.99
    assert await PriceHistory.find().count() == history_before + 1


@respx.mock
async def test_refresh_creates_snapshot_even_when_price_unchanged(
    client, auth_headers, subscribed_product
):
    """Every refresh call records a snapshot — the history is an audit trail."""
    respx.get("https://fakestoreapi.com/products/1").mock(
        return_value=httpx.Response(200, json=FAKESTORE_PRODUCT_1)
    )
    history_before = await PriceHistory.find().count()

    await client.post(
        f"/products/{subscribed_product}/refresh", headers=auth_headers
    )
    assert await PriceHistory.find().count() == history_before + 1


@respx.mock
async def test_refresh_returns_404_when_not_subscribed(
    client, auth_headers_user2, subscribed_product
):
    response = await client.post(
        f"/products/{subscribed_product}/refresh", headers=auth_headers_user2
    )
    assert response.status_code == 404


@respx.mock
async def test_refresh_propagates_external_api_timeout(
    client, auth_headers, subscribed_product
):
    respx.get("https://fakestoreapi.com/products/1").mock(
        side_effect=httpx.TimeoutException("timed out")
    )
    response = await client.post(
        f"/products/{subscribed_product}/refresh", headers=auth_headers
    )
    assert response.status_code == 503
