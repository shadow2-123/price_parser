from datetime import datetime

from sqlalchemy import select, update, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Store, Search, Product, Status, Offer


class SearchesRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_search(
            self,
            product_id: int,
            store: Store,) -> Search:
        search = Search(product_id=product_id, store=store)
        self.session.add(search)
        await self.session.flush()
        return search

    async def get_in_progress(self, store: Store) -> Search | None:
        stmt = (
            select(Search)
            .where(
                Search.store == store,
                Search.status == Status.in_progress,
            )
            .order_by(Search.id)
            .limit(1)
        )

        return await self.session.scalar(stmt)

    async def take_next_search(self, store: Store) -> Search | None:
        next_search_id = (
            select(Search.id)
            .where(
                Search.store == store,
                Search.status == Status.pending,
            )
            .order_by(Search.id)
            .limit(1)
            .scalar_subquery()
        )

        stmt = (
            update(Search)
            .where(
                Search.id == next_search_id,
                Search.status == Status.pending,
            )
            .values(
                status=Status.in_progress,
                started_at=datetime.now(),
                attempts=Search.attempts + 1,
            )
            .returning(Search)
        )

        result = await self.session.scalars(stmt)
        return result.one_or_none()

    async def finish_search(
            self,
            search_id: int,
            status: Status,
            run_number: int,
            error: str | None = None,
    ) -> bool:
        stmt = (
            update(Search)
            .where(
                Search.id == search_id,
                Search.run_number == run_number,
                Search.status == Status.in_progress,
            )
            .values(
                status=status,
                error=error,
                finished_at=datetime.now(),
            )
            .returning(Search.id)
        )

        result = await self.session.scalar(stmt)
        return result is not None

    async def get_searches_by_product(self, product_id: int) -> list[Search]:
        res = await self.session.scalars(select(Search).where(Search.product_id == product_id))
        return list(res.all())

    async def cancel_job_searches(self, job_id: int) -> None:
        product_ids = (
            select(Product.id)
            .where(Product.job_id == job_id)
        )

        stmt = (
            update(Search)
            .where(
                Search.product_id.in_(product_ids),
                Search.status == Status.pending,
            )
            .values(status=Status.canceled,
                    finished_at=datetime.now(),)
        )

        await self.session.execute(stmt)

    async def retry_failed(self, job_id: int) -> int:
        product_ids = select(Product.id).where(Product.job_id == job_id)

        stmt = (
            update(Search)
            .where(
                Search.product_id.in_(product_ids),
                Search.status == Status.failed,
            )
            .values(
                status=Status.pending,
                run_number=Search.run_number + 1,
                error=None,
                started_at=None,
                finished_at=None,
            )
            .returning(Search.id)
        )

        search_ids = list((await self.session.scalars(stmt)).all())

        if search_ids:
            await self.session.execute(
                delete(Offer).where(Offer.search_id.in_(search_ids))
            )

        return len(search_ids)