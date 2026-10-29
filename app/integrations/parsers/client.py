import httpx

from app.config import settings
from app.db.models import Store


class ParserClient:
    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=10.0,
            trust_env=False,
        )

        self.urls = {
            Store.dns: settings.dns_parser_url,
            Store.citilink: settings.citilink_parser_url,
            Store.onlinetrade: settings.onlinetrade_parser_url,
        }

    async def submit(
        self,
        store: Store,
        search_id: int,
        query: str,
        run_number: int,
    ) -> None:
        task_id = (
            f"price_parser:{search_id}"
            if run_number == 1
            else f"price_parser:{search_id}:{run_number}"
        )

        response = await self.client.post(
            f"{self.urls[store]}/tasks",
            json={
                "task_id": task_id,
                "query": query,
                "priority": "low",
                "callback_url": settings.parser_callback_url,
            },
        )

        response.raise_for_status()

        if response.status_code != 202:
            raise RuntimeError(
                f"Unexpected response: {response.status_code}"
            )

        data = response.json()

        if data.get("task_id") != task_id:
            raise RuntimeError("Invalid parser task_id")

    async def close(self) -> None:
        await self.client.aclose()