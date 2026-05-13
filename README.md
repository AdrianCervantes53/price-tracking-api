# Price Tracking API
 
A production-style REST API that tracks product prices from external marketplaces. Users can search products, subscribe to price tracking, and query full price history across multiple sources.
 
Built to demonstrate **layered backend architecture**, **external API integration with retry logic**, **async Python**, and **real-world testing practices**.
 
---
 
## Technical Highlights
 
- **Multi-source architecture** — `FakeStoreClient` and `MercadoLibreClient` share a common interface; a factory (`get_client(source)`) routes operations to the correct client. Adding a new marketplace requires one new client class and one factory entry.
- **Retry with exponential backoff** — `with_retry` is a reusable async utility that retries on `5xx` and `TimeoutException`, and respects `Retry-After` on `429`. Decoupled from any specific client.
- **Global product model** — `Product` documents are shared across all subscribers. The `Subscription` collection models the user↔product relationship. Deleting a subscription never removes price history.
- **Upsert by compound key** — `POST /products` upserts on `(external_id, source)` with a unique MongoDB index, preventing duplicates even under concurrent requests.
- **Security-conscious error handling** — The subscription guard returns `404` in all failure cases (invalid ID, product not found, no subscription) to avoid revealing whether a product exists.
- **~46 integration and unit tests** — HTTP layer mocked with `respx`, database with `mongomock-motor`. Covers happy paths, error propagation, retry behavior, and data isolation between users.
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
├── external_clients/   # httpx clients per marketplace + retry utility + factory
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
 
---
 
## API Reference
 
All endpoints except `/auth/*` require `Authorization: Bearer <token>`.
 
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/auth/register` | No | Register a new user |
| `POST` | `/auth/login` | No | Login — returns JWT |
| `GET` | `/search?q={term}&source={source}` | Yes | Search products (`source`: `fakestore` \| `mercadolibre`, default `fakestore`) |
| `POST` | `/products` | Yes | Subscribe to a product (upsert + subscription) |
| `GET` | `/products` | Yes | List products the authenticated user is subscribed to |
| `GET` | `/products/{id}` | Yes | Product detail — requires active subscription |
| `DELETE` | `/products/{id}` | Yes | Unsubscribe — product and price history are preserved |
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
 
# 2. Search on Mercado Libre
curl "localhost:8000/search?q=mochila&source=mercadolibre" \
  -H "Authorization: Bearer $TOKEN"
 
# 3. Subscribe to a product
curl -s -X POST localhost:8000/products \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"external_id": "MLM123456", "source": "mercadolibre"}'
 
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
A `Product` document is shared across all subscribers. The `Subscription` collection is the many-to-many junction. This means `DELETE /products/{id}` only removes the subscription — price history is never lost, and a `refresh` triggered by one user benefits all subscribers of the same product. The `(external_id, source)` unique index prevents duplicates even under concurrent registration of the same product.
 
**Two-step search → subscribe flow.**
`GET /search` queries the external API and returns candidates without persisting anything. `POST /products` then performs the upsert and creates the subscription. This gives the user explicit control over what they track, and keeps the search endpoint read-only and stateless.
 
**Adapter layer decouples external contracts from the domain model.**
Each client (`FakeStoreClient`, `MercadoLibreClient`) has a `_to_schema` method that maps the external response to the internal `ExternalProductResult`. The rest of the application never sees raw marketplace data. Adding a new source means implementing one class with two methods (`search`, `get_product`) — nothing else changes.
 
**Retry is a reusable utility, not client logic.**
`with_retry(request_func, max_retries, base_delay)` is a standalone async function. It retries on `5xx` and `TimeoutException` with exponential backoff, and respects `Retry-After` on `429`. The ML client uses it; the FakeStore client doesn't need it. Any future client can opt in.
 
**404 in all subscription guard failures.**
`get_product(user_id, product_id)` returns `404` whether the ID is invalid, the product doesn't exist, or the user isn't subscribed. Returning `403` on a missing subscription would reveal that the product exists — a minor but deliberate security choice.
 
**Refresh always creates a snapshot.**
Every call to `POST /products/{id}/refresh` records a new `PriceHistory` entry regardless of whether the price changed. The history is an audit trail of when prices were verified, not just when they changed.
 
---
 
## Running Locally
 
**Requirements:** Docker, Docker Compose.
 
```bash
cp .env.example .env
# Set a strong SECRET_KEY in .env
 
docker compose up
```
 
Interactive API docs: [http://localhost:8000/docs](http://localhost:8000/docs)
 
### Running tests
 
```bash
pip install -r requirements.txt
pytest
```
 
Tests use `mongomock-motor` for an in-memory MongoDB and `respx` to mock all HTTP calls to external APIs — no real network calls, no external dependencies.