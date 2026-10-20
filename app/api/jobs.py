from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory
from app.db.repositories.jobs import JobsRepository
from app.services.jobs import JobsService
from fastapi import Request

router = APIRouter(prefix="/api/jobs", tags=["Jobs"])


async def get_session():
    async with async_session_factory() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_job(
    queries: Annotated[list[str], Body(embed=True)],
    session: SessionDep,
    request: Request,
):
    if not queries:
        raise HTTPException(
            status_code=422,
            detail="Список артикулов не может быть пустым",
        )

    service = JobsService(session)
    job_id = await service.create_job(queries)

    request.app.state.dispatcher.wake_all()

    return {"id": job_id}


@router.get("")
async def get_jobs(session: SessionDep):
    repo = JobsRepository(session)
    jobs = await repo.get_all()

    return [
        {
            "id": job.id,
            "created_at": job.created_at,
            "total_products": job.total_products,
        }
        for job in jobs
    ]


@router.get("/{job_id}")
async def get_job(job_id: int, session: SessionDep):
    repo = JobsRepository(session)
    job = await repo.get_with_details(job_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Задание не найдено",
        )

    return {
        "id": job.id,
        "created_at": job.created_at,
        "total_products": job.total_products,
        "products": [
            {
                "id": product.id,
                "position": product.position,
                "query": product.query,
                "searches": [
                    {
                        "id": search.id,
                        "store": search.store.value,
                        "status": search.status.value,
                        "offers": [
                            {
                                "name": offer.name,
                                "price": str(offer.price),
                                "url": offer.url,
                            }
                            for offer in search.offers
                        ],
                    }
                    for search in product.searches
                ],
            }
            for product in sorted(
                job.products,
                key=lambda p: p.position,
            )
        ],
    }

@router.post("/{job_id}/cancel")
async def cancel_job(job_id: int, session: SessionDep):
    service = JobsService(session)

    success = await service.cancel_job(job_id)

    if not success:
        raise HTTPException(
            status_code=404,
            detail="Задание не найдено",
        )

    return {"id": job_id, "canceled": True}