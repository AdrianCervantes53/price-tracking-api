import httpx
import pytest
import respx

FAKE_PRODUCTS = [
    {"id": 1, "title": "Fjallraven Backpack", "price": 109.95},
    {"id": 2, "title": "Mens Casual Premium Slim Fit T-Shirts", "price": 22.3},
    {"id": 3, "title": "Mens Cotton Jacket", "price": 55.99},
]


@pytest.fixture
async def auth_headers(client):
    await client.post(
        "/auth/register",
        json={"email": "search@example.com", "password": "securepassword"},
    )
    response = await client.post(
        "/auth/login",
        json={"email": "search@example.com", "password": "securepassword"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@respx.mock
async def test_search_returns_filtered_results(client, auth_headers):
    respx.get("https://fakestoreapi.com/products").mock(
        return_value=httpx.Response(200, json=FAKE_PRODUCTS)
    )
    response = await client.get("/search?q=backpack", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["external_id"] == "1"
    assert data[0]["name"] == "Fjallraven Backpack"
    assert data[0]["source"] == "fakestore"
    assert data[0]["currency"] == "USD"


@respx.mock
async def test_search_is_case_insensitive(client, auth_headers):
    respx.get("https://fakestoreapi.com/products").mock(
        return_value=httpx.Response(200, json=FAKE_PRODUCTS)
    )
    response = await client.get("/search?q=JACKET", headers=auth_headers)

    assert response.status_code == 200
    assert len(response.json()) == 1


@respx.mock
async def test_search_no_matches_returns_empty_list(client, auth_headers):
    respx.get("https://fakestoreapi.com/products").mock(
        return_value=httpx.Response(200, json=FAKE_PRODUCTS)
    )
    response = await client.get("/search?q=laptops", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == []


async def test_search_requires_auth(client):
    response = await client.get("/search?q=backpack")
    assert response.status_code == 403


async def test_search_empty_query_returns_422(client, auth_headers):
    response = await client.get("/search?q=", headers=auth_headers)
    assert response.status_code == 422


@respx.mock
async def test_search_fakestore_timeout_returns_503(client, auth_headers):
    respx.get("https://fakestoreapi.com/products").mock(
        side_effect=httpx.TimeoutException("timed out")
    )
    response = await client.get("/search?q=shirt", headers=auth_headers)
    assert response.status_code == 503


@respx.mock
async def test_search_fakestore_server_error_returns_502(client, auth_headers):
    respx.get("https://fakestoreapi.com/products").mock(
        return_value=httpx.Response(500)
    )
    response = await client.get("/search?q=shirt", headers=auth_headers)
    assert response.status_code == 502
