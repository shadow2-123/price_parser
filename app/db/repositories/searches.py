from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Store, Search, Product, Status


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

    async def get_next_search(self, store: Store) -> Search | None:
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
                status=Status.running,
                started_at=datetime.now(),
                attempts=Search.attempts + 1,
            )
            .returning(Search)
        )

        result = await self.session.scalars(stmt)
        return result.one_or_none()

    async def finish_search(self,
                            search_id: int,
                            status: Status,
                            error: str | None = None) -> None:
        res = await self.session.scalars(select(Search).where(Search.id == search_id))
        search = res.first()
        if search:
            search.status = status
            search.error = error
            search.finished_at = datetime.now()

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
            .values(status=Status.canceled)
        )

        await self.session.execute(stmt)