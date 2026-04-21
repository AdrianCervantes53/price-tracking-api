import pytest
from httpx import AsyncClient


async def test_register_returns_token(client: AsyncClient):
    response = await client.post(
        "/auth/register",
        json={"email": "user@example.com", "password": "strongpassword"},
    )
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert len(data["access_token"]) > 0


async def test_register_duplicate_email_returns_409(client: AsyncClient):
    payload = {"email": "dup@example.com", "password": "strongpassword"}
    await client.post("/auth/register", json=payload)
    response = await client.post("/auth/register", json=payload)
    assert response.status_code == 409
    assert "already registered" in response.json()["detail"]


async def test_register_invalid_email_returns_422(client: AsyncClient):
    response = await client.post(
        "/auth/register",
        json={"email": "not-an-email", "password": "strongpassword"},
    )
    assert response.status_code == 422


async def test_register_missing_password_returns_422(client: AsyncClient):
    response = await client.post(
        "/auth/register",
        json={"email": "user@example.com"},
    )
    assert response.status_code == 422


async def test_login_valid_credentials_returns_token(client: AsyncClient):
    payload = {"email": "login@example.com", "password": "mypassword"}
    await client.post("/auth/register", json=payload)

    response = await client.post("/auth/login", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


async def test_login_wrong_password_returns_401(client: AsyncClient):
    await client.post(
        "/auth/register",
        json={"email": "wrong@example.com", "password": "correctpassword"},
    )
    response = await client.post(
        "/auth/login",
        json={"email": "wrong@example.com", "password": "wrongpassword"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


async def test_login_unknown_email_returns_401(client: AsyncClient):
    response = await client.post(
        "/auth/login",
        json={"email": "ghost@example.com", "password": "whatever"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


async def test_login_token_is_usable_on_protected_route(client: AsyncClient):
    """Token obtenido en login debe autenticar rutas protegidas (GET /products)."""
    payload = {"email": "protected@example.com", "password": "securepassword"}
    await client.post("/auth/register", json=payload)
    login_response = await client.post("/auth/login", json=payload)
    token = login_response.json()["access_token"]

    response = await client.get(
        "/products",
        headers={"Authorization": f"Bearer {token}"},
    )
    # GET /products está en 501 — pero si llegamos a 501, el token fue válido (no 401)
    assert response.status_code != 401


async def test_register_accepts_password_longer_than_72_bytes(client: AsyncClient):
    long_password = "a" * 100
    payload = {"email": "longpw@example.com", "password": long_password}

    response = await client.post("/auth/register", json=payload)
    assert response.status_code == 201

    login_response = await client.post("/auth/login", json=payload)
    assert login_response.status_code == 200
