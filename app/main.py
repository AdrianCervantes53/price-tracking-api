from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.database import init_db
from app.routers import auth, prices, products, search


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="Price Tracking API",
    description=(
        "Track product prices from external marketplaces. "
        "Supports search, subscriptions, and full price history."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(search.router, prefix="/search", tags=["search"])
app.include_router(products.router, prefix="/products", tags=["products"])
app.include_router(prices.router, prefix="/products", tags=["prices"])


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok"}
