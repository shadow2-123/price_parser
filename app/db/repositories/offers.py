from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Offer


class OffersRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_offer(self, search_id: int,
                           name: str,
                           price: Decimal,
                           url: str) -> Offer:
        offer = Offer(search_id=search_id, name=name, price=price, url=url)
        self.session.add(offer)
        await self.session.flush()
        return offer

    async def get_offers_by_search(self, search_id: int) -> list[Offer]:
        res = await self.session.scalars(select(Offer).where(Offer.search_id == search_id))
        return list(res.all())