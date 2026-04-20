# Price Tracking API

A backend service that tracks product prices from external marketplaces. Built as a portfolio project demonstrating real-world API integration, layered architecture, JWT authentication, and async Python.

## Problem

Users have no automated way to monitor price changes, query price history, or detect buying opportunities. Doing this manually across marketplaces is inefficient and doesn't scale.

## Stack

| Layer | Tool | Reason |
|-------|------|--------|
| Framework | FastAPI | Native async, automatic OpenAPI docs, Pydantic integration |
| ODM | Beanie | Async ODM on top of Motor, Pydantic-compatible document models |
| HTTP Client | httpx | Native async, explicit timeouts and retry support |
| Auth | python-jose + passlib | Standard JWT, secure bcrypt password hashing |
| Database | MongoDB | Schema flexibility for inconsistent external API responses |
| Testing | pytest + respx | Async-friendly test runner, HTTP-level mocks for httpx |
| Infra | Docker + Docker Compose | One-command local setup |

## Architecture

```
app/
 ├── routers/            # HTTP layer — request/response validation, route definitions
 ├── services/           # Business logic and orchestration
 ├── external_clients/   # External API consumption (httpx, retry, headers)
 ├── repositories/       # MongoDB CRUD via Beanie
 ├── models/             # Beanie documents + Pydantic schemas
 └── core/               # Config, JWT security, FastAPI dependencies
```

## Running the Project

```bash
cp .env.example .env
# Edit .env and set a strong SECRET_KEY

docker compose up
```

API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

## Running Tests

```bash
pip install -r requirements.txt
pytest
```

## API Endpoints

All endpoints except `/auth/*` require `Authorization: Bearer <token>` header.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/auth/register` | ❌ | Register a new user |
| `POST` | `/auth/login` | ❌ | Login — returns JWT |
| `GET` | `/search?q={term}` | ✅ | Search products in external marketplace |
| `POST` | `/products` | ✅ | Subscribe to a product (upsert + subscription) |
| `GET` | `/products` | ✅ | List products the user is subscribed to |
| `GET` | `/products/{id}` | ✅ | Product detail (requires active subscription) |
| `DELETE` | `/products/{id}` | ✅ | Unsubscribe (product and history are preserved) |
| `GET` | `/products/{id}/history` | ✅ | Full price history ordered by date desc |
| `POST` | `/products/{id}/refresh` | ✅ | Fetch current price and record a new snapshot |

## Key Design Decisions

**Products are global, not per-user.** `Product` documents are shared across all subscribers. The `Subscription` collection models the user↔product relationship. `DELETE /products/{id}` removes the subscription only — price history is never lost.

**Two-step search and register flow.** `GET /search` queries the external API and returns candidates without persisting anything. `POST /products` performs an upsert by `(external_id, source)` and creates the subscription.

**External API integration in phases.** Phase 1 targets Fake Store API (no auth, predictable data) to validate the full architectural flow end-to-end. Phase 2 migrates to Mercado Libre (OAuth, rate limiting, variable response schemas) through an explicit adapter layer that decouples the external contract from the internal domain model.

**Error strategy.** Timeouts and 5xx responses trigger exponential backoff (max 3–5 retries). 429 responses respect `Retry-After`. 4xx errors propagate immediately to the client.

## Development Phases

| Phase | Scope |
|-------|-------|
| 1 | Setup, models, JWT auth (register + login) |
| 2 | Fake Store client, search, product upsert, subscriptions |
| 3 | Price history, refresh endpoint, unit + integration tests |
| 4 | Mercado Libre migration — OAuth, adapter layer, retry logic |
| 5 *(optional)* | Cache (TTL), background jobs, Watchlist with price alerts |
