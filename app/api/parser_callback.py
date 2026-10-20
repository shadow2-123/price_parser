import re
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.db.models import Search, Status
from app.db.repositories.offers import OffersRepository
from app.db.repositories.searches import SearchesRepository
from app.db.session import async_session_factory


router = APIRouter(tags=["Parsers"])


class ParserOffer(BaseModel):
    name: str
    price: Decimal
    url: str


class ParserResult(BaseModel):
    task_id: str
    status: Literal["found", "not_found", "failed"]
    offers: list[ParserOffer] = Field(default_factory=list)
    error: str | None = None


@router.post("/api/parser-callback")
async def parser_callback(
    payload: ParserResult,
    request: Request,
):
    match = re.fullmatch(
        r"price_parser:([1-9][0-9]*)",
        payload.task_id,
    )

    if match is None:
        raise HTTPException(
            status_code=400,
            detail="Invalid task_id",
        )

    search_id = int(match.group(1))
    final_status = Status(payload.status)

    async with async_session_factory() as session:
        async with session.begin():
            searches = SearchesRepository(session)
            offers = OffersRepository(session)

            updated = await searches.finish_search(
                search_id=search_id,
                status=final_status,
                error=payload.error,
            )

            if updated:
                for offer in payload.offers:
                    await offers.create_offer(
                        search_id=search_id,
                        name=offer.name,
                        price=offer.price,
                        url=offer.url,
                    )

            else:
                existing = await session.get(
                    Search,
                    search_id,
                )

                if existing is None:
                    raise HTTPException(
                        status_code=404,
                        detail="Search not found",
                    )

                if existing.status != final_status:
                    raise HTTPException(
                        status_code=409,
                        detail="Search has different status",
                    )

            store = await session.scalar(
                select(Search.store)
                .where(Search.id == search_id)
            )

    request.app.state.dispatcher.wake(store)

    return {
        "task_id": payload.task_id,
        "status": "received",
    }