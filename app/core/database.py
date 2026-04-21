import motor.motor_asyncio
from beanie import init_beanie

from app.core.config import settings
from app.models.user import User
from app.models.product import Product
from app.models.subscription import Subscription
from app.models.price_history import PriceHistory


async def init_db() -> None:
    client = motor.motor_asyncio.AsyncIOMotorClient(settings.mongodb_url)
    await init_beanie(
        database=client[settings.mongodb_db_name],
        document_models=[User, Product, Subscription, PriceHistory],
    )
