from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Product


class ProductsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_job(self, job_id: int) -> list[Product]:
        res = await self.session.scalars(select(Product).where(Product.job_id == job_id))
        return list(res.all())


    async def create_product(self, job_id: int,
                             query: str,
                             position: int,) -> Product:
        product = Product(job_id=job_id,
                          query=query,
                          position=position)
        self.session.add(product)
        await self.session.flush()
        return product