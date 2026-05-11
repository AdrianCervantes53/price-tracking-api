from app.models.product import Product
from app.models.subscription import Subscription


class SubscriptionRepository:
    async def get_by_user_and_product(
        self, user_id: str, product_id: str
    ) -> Subscription | None:
        return await Subscription.find_one(
            Subscription.user_id == user_id,
            Subscription.product_id == product_id,
        )

    async def create(self, user_id: str, product_id: str) -> Subscription:
        subscription = Subscription(user_id=user_id, product_id=product_id)
        await subscription.insert()
        return subscription

    async def get_subscribed_products(self, user_id: str) -> list[Product]:
        """Returns all products the user is currently subscribed to."""
        subscriptions = await Subscription.find(
            Subscription.user_id == user_id
        ).to_list()
        products = []
        for sub in subscriptions:
            product = await Product.get(sub.product_id)
            if product:
                products.append(product)
        return products

    async def delete(self, user_id: str, product_id: str) -> bool:
        """
        Removes the subscription for the given user and product.
        Returns True if deleted, False if no subscription existed.
        """
        subscription = await self.get_by_user_and_product(user_id, product_id)
        if not subscription:
            return False
        await subscription.delete()
        return True
