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

FAKESTORE_PRODUCT_2 = {
    "id": 2,
    "title": "Mens Casual Shirt",
    "price": 22.3,
    "category": "men's clothing",
    "description": "Slim fit shirt",
    "image": "https://fakestoreapi.com/img/2.jpg",
    "rating": {"rate": 4.1, "count": 259},
}


@pytest.fixture
async def auth_headers(client):
    await client.post(
        "/auth/register",
        json={"email": "user@example.com", "password": "securepassword"},
    )
    response = await client.post(
        "/auth/login",
        json={"email": "user@example.com", "password": "securepassword"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def auth_headers_user2(client):
    await client.post(
        "/auth/register",
        json={"email": "user2@example.com", "password": "securepassword"},
    )
    response = await client.post(
        "/auth/login",
        json={"email": "user2@example.com", "password": "securepassword"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@respx.mock
async def test_register_new_product_creates_product_subscription_and_snapshot(
    client, auth_headers
):
    respx.get("https://fakestoreapi.com/products/1").mock(
        return_value=httpx.Response(200, json=FAKESTORE_PRODUCT_1)
    )
    response = await client.post(
        "/products",
        json={"external_id": "1", "source": "fakestore"},
        headers=auth_headers,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["external_id"] == "1"
    assert data["name"] == "Fjallraven Backpack"
    assert data["current_price"] == 109.95
    assert data["currency"] == "USD"
    assert await Product.find().count() == 1
    assert await Subscription.find().count() == 1
    assert await PriceHistory.find().count() == 1


@respx.mock
async def test_register_existing_product_creates_only_subscription(
    client, auth_headers, auth_headers_user2
):
    """If the product already exists globally, only a new Subscription is created."""
    respx.get("https://fakestoreapi.com/products/1").mock(
        return_value=httpx.Response(200, json=FAKESTORE_PRODUCT_1)
    )

    await client.post(
        "/products",
        json={"external_id": "1", "source": "fakestore"},
        headers=auth_headers,
    )
    assert await Product.find().count() == 1
    assert await PriceHistory.find().count() == 1  # snapshot only created once

    await client.post(
        "/products",
        json={"external_id": "1", "source": "fakestore"},
        headers=auth_headers_user2,
    )

    assert await Product.find().count() == 1  # still one global product
    assert await Subscription.find().count() == 2  # one per user
    assert await PriceHistory.find().count() == 1  # no new snapshot


@respx.mock
async def test_register_duplicate_subscription_returns_409(client, auth_headers):
    respx.get("https://fakestoreapi.com/products/1").mock(
        return_value=httpx.Response(200, json=FAKESTORE_PRODUCT_1)
    )

    await client.post(
        "/products",
        json={"external_id": "1", "source": "fakestore"},
        headers=auth_headers,
    )
    response = await client.post(
        "/products",
        json={"external_id": "1", "source": "fakestore"},
        headers=auth_headers,
    )

    assert response.status_code == 409
    assert "Already subscribed" in response.json()["detail"]


@respx.mock
async def test_list_products_returns_only_user_subscriptions(
    client, auth_headers, auth_headers_user2
):
    respx.get("https://fakestoreapi.com/products/1").mock(
        return_value=httpx.Response(200, json=FAKESTORE_PRODUCT_1)
    )
    respx.get("https://fakestoreapi.com/products/2").mock(
        return_value=httpx.Response(200, json=FAKESTORE_PRODUCT_2)
    )

    await client.post(
        "/products",
        json={"external_id": "1", "source": "fakestore"},
        headers=auth_headers,
    )
    await client.post(
        "/products",
        json={"external_id": "2", "source": "fakestore"},
        headers=auth_headers_user2,
    )

    response = await client.get("/products", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["external_id"] == "1"


async def test_list_products_empty_for_new_user(client, auth_headers):
    response = await client.get("/products", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == []


@respx.mock
async def test_delete_subscription_removes_only_subscription(client, auth_headers):
    """DELETE unsubscribes the user but preserves the product and price history."""
    respx.get("https://fakestoreapi.com/products/1").mock(
        return_value=httpx.Response(200, json=FAKESTORE_PRODUCT_1)
    )

    post_response = await client.post(
        "/products",
        json={"external_id": "1", "source": "fakestore"},
        headers=auth_headers,
    )
    product_id = post_response.json()["id"]

    delete_response = await client.delete(
        f"/products/{product_id}", headers=auth_headers
    )
    assert delete_response.status_code == 204

    assert await Product.find().count() == 1
    assert await PriceHistory.find().count() == 1
    assert await Subscription.find().count() == 0


async def test_delete_nonexistent_subscription_returns_404(client, auth_headers):
    response = await client.delete(
        "/products/000000000000000000000001", headers=auth_headers
    )
    assert response.status_code == 404


@respx.mock
async def test_register_product_not_found_in_external_api_returns_404(
    client, auth_headers
):
    respx.get("https://fakestoreapi.com/products/999").mock(
        return_value=httpx.Response(404)
    )
    response = await client.post(
        "/products",
        json={"external_id": "999", "source": "fakestore"},
        headers=auth_headers,
    )
    assert response.status_code == 404


async def test_register_product_requires_auth(client):
    response = await client.post(
        "/products", json={"external_id": "1", "source": "fakestore"}
    )
    assert response.status_code == 403
