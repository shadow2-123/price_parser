from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Store, Search, Product, Status


class SearchesRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_search(
            self,
            product_id: int,
            store: Store,) -> Search:
        search = Search(product=product_id, store=store)
        self.session.add(search)
        await self.session.flush()
        return search

    async def get_next_search(self, store: Store) -> Search | None:
        res = await self.session.scalars(select(Search).where(Search.store == store and
                                                             Search.status == Status.pending))
        return res.first()

    async def mark_finished(self,
                            search_id: int,
                            status: Status,
                            error: str | None = None) -> None:
        res = await self.session.scalars(select(Search).where(Search.id == search_id))
        search = res.first()
        if search:
            search.status = status
            search.error = error