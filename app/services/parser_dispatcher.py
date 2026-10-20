import asyncio
import logging

from sqlalchemy import select

from app.db.models import Product, Store
from app.db.repositories.searches import SearchesRepository
from app.db.session import async_session_factory
from app.integrations.parsers.client import ParserClient


logger = logging.getLogger(__name__)


class ParserDispatcher:
    def __init__(self):
        self.client = ParserClient()

        self.events = {
            store: asyncio.Event()
            for store in Store
        }

        self.workers: list[asyncio.Task] = []

    async def start(self) -> None:
        for store in Store:
            task = asyncio.create_task(
                self._worker(store),
                name=f"parser-dispatcher-{store.value}",
            )
            self.workers.append(task)

        self.wake_all()

    async def stop(self) -> None:
        for task in self.workers:
            task.cancel()

        await asyncio.gather(
            *self.workers,
            return_exceptions=True,
        )

        await self.client.close()

    def wake(self, store: Store) -> None:
        self.events[store].set()

    def wake_all(self) -> None:
        for store in Store:
            self.wake(store)

    @staticmethod
    async def _get_task(
            store: Store,
    ) -> tuple[int, str] | None:
        async with async_session_factory() as session:
            async with session.begin():
                repo = SearchesRepository(session)

                search = await repo.get_queued(store)

                if search is None:
                    search = await repo.take_next_search(store)

                if search is None:
                    return None

                query = await session.scalar(
                    select(Product.query)
                    .where(Product.id == search.product_id)
                )

                if query is None:
                    raise RuntimeError(
                        f"Product not found for search {search.id}"
                    )

                return search.id, query

    async def _worker(self, store: Store) -> None:
        event = self.events[store]

        while True:
            await event.wait()
            event.clear()
            search_id = 0
            while True:
                try:
                    task = await self._get_task(store)
                    if task is None:
                        break

                    search_id, query = task

                    async with async_session_factory() as session:
                        async with session.begin():
                            await SearchesRepository(session).set_queued(search_id)

                    await self.client.submit(
                        store=store,
                        search_id=search_id,
                        query=query,
                    )

                except Exception:
                    async with async_session_factory() as session:
                        async with session.begin():
                            await SearchesRepository(session).set_failed(search_id)
                    logger.exception(
                        "Failed to submit search %s to %s",
                        search_id,
                        store.value,
                    )

                    await asyncio.sleep(15)
                    continue

                break