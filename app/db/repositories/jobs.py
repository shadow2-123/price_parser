from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Job, Product, Search, Status, Store


class JobsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, job_id: int) -> Job | None:
        res = await self.session.execute(select(Job).where(Job.id == job_id))
        return res.scalar_one_or_none()

    async def get_all(self) -> list[Job]:
        res = await self.session.scalars(select(Job))
        return list(res.all())

    async def create_job(self, total_products: int) -> Job:
        job = Job(total_products=total_products)
        self.session.add(job)
        await self.session.flush()
        return job

    async def get_with_details(self, job_id: int) -> Job | None:
        stmt = (
            select(Job)
            .options(
                selectinload(Job.products)
                .selectinload(Product.searches)
                .selectinload(Search.offers)
            )
            .where(Job.id == job_id)
        )

        return await self.session.scalar(stmt)

    async def get_progress(self, job_id: int) -> dict:
        stmt = (
            select(
                Search.store,
                Search.status,
                func.count(Search.id),
            )
            .join(Product, Search.product_id == Product.id)
            .where(Product.job_id == job_id)
            .group_by(Search.store, Search.status)
        )

        result = await self.session.execute(stmt)

        progress = {
            store.value: {
                status.value: 0
                for status in Status
            }
            for store in Store
        }

        for store, status, count in result.all():
            progress[store.value][status.value] = count

        return progress