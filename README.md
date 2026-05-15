# Price Tracking API

A production-style REST API that tracks prices from external data sources. Users can search assets, subscribe to price tracking, and query full price history across multiple sources.

Built to demonstrate **layered backend architecture**, **external API integration with retry logic**, **async Python**, and **real-world testing practices**.

---

## Technical Highlights

- **Multi-source architecture** — `FakeStoreClient` and `CoinGeckoClient` share a common interface; a factory (`get_client(source)`) routes operations to the correct client. Adding a new source requires one new client class and one factory entry.
- **Batched price fetching** — `CoinGeckoClient.search` retrieves prices for all results in a single call using CoinGecko's batched `/simple/price` endpoint, rather than N concurrent quote calls.
- **Concurrent external calls** — `CoinGeckoClient.get_product` makes two requests concurrently via `asyncio.gather`: one for the price and one for the coin metadata.
- **Retry with exponential backoff** — `with_retry` is a reusable async utility that retries on `5xx` and `TimeoutException`, and respects `Retry-After` on `429`. Decoupled from any specific client.
- **Global product model** — `Product` documents are shared across all subscribers. The `Subscription` collection models the user↔product relationship. Deleting a subscription never removes price history.
- **Upsert by compound key** — `POST /products` upserts on `(external_id, source)` with a unique MongoDB index, preventing duplicates even under concurrent requests.
- **Security-conscious error handling** — The subscription guard returns `404` in all failure cases (invalid ID, product not found, no subscription) to avoid revealing whether a product exists.
- **~68 integration and unit tests** — HTTP layer mocked with `respx`, database with `mongomock-motor`. Covers happy paths, error propagation, retry behavior, price-unchanged snapshots, and data isolation between users.

---

## Stack

| Layer | Tool | Reason |
|-------|------|--------|
| Framework | FastAPI | Native async, automatic OpenAPI docs, Pydantic integration |
| ODM | Beanie | Async ODM on top of Motor, natural fit with Pydantic models |
| HTTP Client | httpx | Native async, composable with custom retry logic |
| Auth | python-jose + passlib | Standard JWT, bcrypt password hashing |
| Database | MongoDB | Schema flexibility for inconsistent external API responses |
| Testing | pytest + respx + mongomock-motor | Async test runner, HTTP-level mocks, in-memory MongoDB |
| Infra | Docker + Docker Compose | One-command local setup |

---

## Architecture

```
app/
├── routers/            # HTTP layer — validation, route definitions, response mapping
├── services/           # Business logic and orchestration
├── external_clients/   # httpx clients per source + retry utility + factory
├── repositories/       # MongoDB CRUD via Beanie (one class per collection)
├── models/             # Beanie documents (User, Product, Subscription, PriceHistory)
├── schemas/            # Pydantic request/response models (per domain)
└── core/               # Config, JWT security, FastAPI dependencies
```

### Request flow — `POST /products`

```
Router → product_service.register_product()
           ├── get_client(source).get_product(external_id)   # fetch fresh data
           ├── product_repo.upsert()                         # find or create Product
           ├── sub_repo.get_by_user_and_product()            # check for duplicate
           ├── sub_repo.create()                             # create Subscription
           └── price_history_repo.create_snapshot()          # first snapshot if new
```

### CoinGeckoClient — batched search + concurrent get_product

`search` fetches prices for all results in **one** batched call to `/simple/price`, avoiding N sequential or concurrent quote requests. `get_product` makes two concurrent calls to minimize latency.

```
CoinGeckoClient.search("bitcoin")
   ├── GET /search?query=bitcoin        # returns coin ids + names
   └── GET /simple/price?ids=a,b,c,...  # one batched call for all prices

CoinGeckoClient.get_product("bitcoin")
   ├── GET /simple/price?ids=bitcoin  ─┐  (concurrent via asyncio.gather)
   └── GET /coins/bitcoin              ─┘
```

---

## Data Sources

### Active sources

**FakeStore API** (`source=fakestore`) — Static product catalog with no authentication. Used as the initial data source to validate the full architecture (upsert, subscriptions, price history, refresh) before integrating a real external API.

**CoinGecko API** (`source=coingecko`) — Real-time cryptocurrency prices. Free Demo tier provides 30 calls/minute with a monthly cap of 10,000 calls. Prices change 24/7 with no market-hours restriction, making the price history feature genuinely meaningful at any time of day. Get a free Demo key at [coingecko.com/en/api](https://www.coingecko.com/en/api).

The `external_id` for CoinGecko is the coin's slug (e.g. `bitcoin`, `ethereum`), not the ticker symbol. The search endpoint returns the slug so users can copy it directly into `POST /products`.

> **ToS note:** CoinGecko's Terms of Service permit building applications that display and charge for services using CoinGecko data. The restriction is on sub-licensing or reselling API access itself — not on serving coin prices to end users. This project can be deployed publicly without the ToS constraints that apply to Finnhub.

### Reference implementations (not exposed in public API)

**Finnhub Stock API** — `FinnhubClient` is retained in the codebase as a reference implementation of the concurrent-calls pattern (`asyncio.gather` for quote + search) and the price-fallback strategy (previous close when market is closed). Its tests pass with `respx` mocks. Not exposed as `source=finnhub` because Finnhub's ToS prohibit redistribution of data to third parties without written approval.

**MercadoLibre API** — `MercadoLibreClient` is retained as a reference implementation of the retry + adapter pattern. Not exposed because ML restricted public access to their search and item endpoints in 2024–2025; both return `403 Forbidden` in production.

### Why crypto instead of stocks or a marketplace?

The original goal was to track product prices from a real marketplace. During evaluation, several candidates were ruled out:

- **MercadoLibre** — client implemented, but API returns `403` on all public endpoints since 2024–2025.
- **eBay Browse API** and **Best Buy API** — ToS explicitly prohibit price tracking use cases.
- **Amazon** — no public API.
- **Finnhub** — functional and well-documented, but ToS prohibit redistribution of data to third parties.
- **Steam** — no official search endpoint; game prices are static outside of seasonal sales.

CoinGecko turned out to be the best fit: permissive ToS for application use, a generous free tier, an official search endpoint, and prices that change continuously 24/7 — making the price history feature meaningful without any market-hours constraint. The domain shift required zero model changes; `external_id` became a coin slug (`bitcoin`) instead of a product ID, and everything else stayed the same.

---

## API Reference

All endpoints except `/auth/*` require `Authorization: Bearer <token>`.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/auth/register` | No | Register a new user |
| `POST` | `/auth/login` | No | Login — returns JWT |
| `GET` | `/search?q={term}&source={source}` | Yes | Search assets (`source`: `fakestore` \| `coingecko`, default `fakestore`) |
| `POST` | `/products` | Yes | Subscribe to an asset (upsert + subscription) |
| `GET` | `/products` | Yes | List assets the authenticated user is subscribed to |
| `GET` | `/products/{id}` | Yes | Asset detail — requires active subscription |
| `DELETE` | `/products/{id}` | Yes | Unsubscribe — asset and price history are preserved |
| `GET` | `/products/{id}/history` | Yes | Full price history ordered by date desc |
| `POST` | `/products/{id}/refresh` | Yes | Fetch current price and record a new snapshot |

### Example flow

```bash
# 1. Register and login
curl -s -X POST localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "secret123"}'

TOKEN=$(curl -s -X POST localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "secret123"}' | jq -r .access_token)

# 2. Search cryptocurrencies on CoinGecko
curl "localhost:8000/search?q=bitcoin&source=coingecko" \
  -H "Authorization: Bearer $TOKEN"

# 3. Subscribe to a coin (use the slug from search results as external_id)
curl -s -X POST localhost:8000/products \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"external_id": "bitcoin", "source": "coingecko"}'

# 4. Check price history
curl "localhost:8000/products/{id}/history" \
  -H "Authorization: Bearer $TOKEN"

# 5. Refresh price
curl -X POST "localhost:8000/products/{id}/refresh" \
  -H "Authorization: Bearer $TOKEN"
```

---

## Key Design Decisions

**Products are global, not per-user.**
A `Product` document is shared across all subscribers. The `Subscription` collection is the many-to-many junction. This means `DELETE /products/{id}` only removes the subscription — price history is never lost, and a `refresh` triggered by one user benefits all subscribers of the same product. The `(external_id, source)` unique index prevents duplicates even under concurrent registration of the same asset.

**Two-step search → subscribe flow.**
`GET /search` queries the external API and returns candidates without persisting anything. `POST /products` then performs the upsert and creates the subscription. This gives the user explicit control over what they track, and keeps the search endpoint read-only and stateless.

**Adapter layer decouples external contracts from the domain model.**
Each client (`FakeStoreClient`, `CoinGeckoClient`) has a `_to_schema` method that maps the external response to the internal `ExternalProductResult`. The rest of the application never sees raw external API data. Adding a new source means implementing one class with two methods (`search`, `get_product`) — nothing else changes.

**Batched price fetching over N concurrent calls.**
CoinGecko's `/simple/price` endpoint accepts a comma-separated list of coin ids, returning all prices in a single response. `CoinGeckoClient.search` uses this to replace the N concurrent quote calls that `FinnhubClient` required, reducing both latency and rate-limit consumption.

**Retry is a reusable utility, not client logic.**
`with_retry(request_func, max_retries, base_delay)` is a standalone async function. It retries on `5xx` and `TimeoutException` with exponential backoff, and respects `Retry-After` on `429`. `CoinGeckoClient` and `MercadoLibreClient` use it; `FakeStoreClient` opts out. Any future client can opt in.

**404 in all subscription guard failures.**
`get_product(user_id, product_id)` returns `404` whether the ID is invalid, the product doesn't exist, or the user isn't subscribed. Returning `403` on a missing subscription would reveal that the product exists — a minor but deliberate security choice.

**Refresh always creates a snapshot.**
Every call to `POST /products/{id}/refresh` records a new `PriceHistory` entry regardless of whether the price changed. The history is an audit trail of when prices were verified, not just when they changed.

**Source selection is ToS-aware by design.**
The public `source` field accepts only `fakestore` and `coingecko`. `FinnhubClient` and `MercadoLibreClient` are retained in the codebase as reference implementations — their tests pass, but they are not reachable through the public API. This is a deliberate architectural decision documented here and in the factory, not an oversight.

---

## Running Locally

**Requirements:** Docker, Docker Compose. No API key required to run the app — CoinGecko works without one, though a free Demo key improves rate limit stability.

```bash
cp .env.example .env
# Set SECRET_KEY in .env
# Optionally set COINGECKO_API_KEY for stable 30 req/min (free at coingecko.com/en/api)

docker compose up
```

Interactive API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

### Running tests

```bash
pip install -r requirements.txt
pytest
```

Tests use `mongomock-motor` for an in-memory MongoDB and `respx` to mock all HTTP calls to external APIs — no real network calls, no API key required for testing.
