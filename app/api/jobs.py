import asyncio
from io import BytesIO
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory
from app.db.repositories.jobs import JobsRepository
from app.services.excel_handler import extract_queries, export_job_excel
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

@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_job(
    file: Annotated[UploadFile, File()],
    session: SessionDep,
    request: Request,
):
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(
            status_code=422,
            detail="Поддерживаются только .xlsx файлы",
        )

    data = await file.read()

    try:
        queries = await asyncio.to_thread(extract_queries, data)
    except Exception:
        raise HTTPException(
            status_code=422,
            detail="Не удалось прочитать Excel-файл",
        )

    if not queries:
        raise HTTPException(
            status_code=422,
            detail="Excel-файл не содержит артикулов",
        )

    service = JobsService(session)
    job_id = await service.create_job(queries)

    request.app.state.dispatcher.wake_all()

    return {"id": job_id}


@router.get("/{job_id}/export")
async def export_job(
    job_id: int,
    session: SessionDep,
):
    repo = JobsRepository(session)
    job = await repo.get_with_details(job_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Задание не найдено",
        )

    data = await asyncio.to_thread(export_job_excel, job)

    return StreamingResponse(
        BytesIO(data),
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": (
                f'attachment; filename="job_{job_id}.xlsx"'
            ),
        },
    )


@router.get("/{job_id}/progress")
async def get_job_progress(
    job_id: int,
    session: SessionDep,
):
    repo = JobsRepository(session)

    job = await repo.get(job_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Задание не найдено",
        )

    progress = await repo.get_progress(job_id)

    finished_statuses = (
        "found",
        "not_found",
        "failed",
        "canceled",
    )

    stores = {}
    overall_total = 0
    overall_completed = 0

    for store, statuses in progress.items():
        total = sum(statuses.values())

        completed = sum(
            statuses[status]
            for status in finished_statuses
        )

        stores[store] = {
            "total": total,
            "completed": completed,
            "percent": round(
                completed / total * 100, 1
            ) if total else 0.0,
            "statuses": statuses,
        }

        overall_total += total
        overall_completed += completed

    return {
        "job_id": job_id,
        "overall": {
            "total": overall_total,
            "completed": overall_completed,
            "percent": round(
                overall_completed / overall_total * 100, 1
            ) if overall_total else 0.0,
        },
        "stores": stores,
    }