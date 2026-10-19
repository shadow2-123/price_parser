from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db.init import init_db
from app.db.session import async_engine
from app.api.jobs import router as jobs_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    try:
        yield
    finally:
        await async_engine.dispose()



app = FastAPI(lifespan=lifespan)
app.include_router(jobs_router)