from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Job


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