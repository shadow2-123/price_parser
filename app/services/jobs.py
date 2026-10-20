from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Store
from app.db.repositories.jobs import JobsRepository
from app.db.repositories.products import ProductsRepository
from app.db.repositories.searches import SearchesRepository


class JobsService:
    def __init__(self, session: AsyncSession):
        self.session = session

        self.jobs = JobsRepository(session)
        self.products = ProductsRepository(session)
        self.searches = SearchesRepository(session)

    async def create_job(self, queries: list[str]) -> int:
        async with self.session.begin():
            job = await self.jobs.create_job(
                total_products=len(queries)
            )

            for position, query in enumerate(queries):
                product = await self.products.create_product(
                    job_id=job.id,
                    query=query,
                    position=position,
                )

                for store in Store:
                    await self.searches.create_search(
                        product_id=product.id,
                        store=store,
                    )

            job_id = job.id

        return job_id

    async def cancel_job(self, job_id: int) -> bool:
        async with self.session.begin():
            job = await self.jobs.get(job_id)

            if job is None:
                return False

            await self.searches.cancel_job_searches(job_id)

        return True