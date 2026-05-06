from app.models.product import Product


class ProductRepository:
    async def get_by_id(self, product_id: str) -> Product | None:
        return await Product.get(product_id)

    async def find_by_external(self, external_id: str, source: str) -> Product | None:
        return await Product.find_one(
            Product.external_id == external_id,
            Product.source == source,
        )

    async def upsert(
        self,
        external_id: str,
        source: str,
        name: str,
        price: float,
        currency: str,
    ) -> tuple[Product, bool]:
        """
        Finds or creates a product by (external_id, source).
        Returns (product, is_new) — is_new is True only when a new document was inserted.
        """
        existing = await self.find_by_external(external_id, source)
        if existing:
            return existing, False

        product = Product(
            external_id=external_id,
            source=source,
            name=name,
            current_price=price,
            currency=currency,
        )
        await product.insert()
        return product, True
