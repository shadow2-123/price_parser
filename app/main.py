from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.jobs import router as jobs_router
from app.api.parser_callback import router as parser_router
from app.db.init import init_db
from app.db.session import async_engine
from app.services.parser_dispatcher import ParserDispatcher
from pathlib import Path
from fastapi.staticfiles import StaticFiles

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    dispatcher = ParserDispatcher()
    app.state.dispatcher = dispatcher

    await dispatcher.start()

    try:
        yield
    finally:
        await dispatcher.stop()
        await async_engine.dispose()


app = FastAPI(lifespan=lifespan)
app.include_router(jobs_router)
app.include_router(parser_router)
app.mount(
    "/",
    StaticFiles(
        directory=Path(__file__).resolve().parent.parent / "static",
        html=True,
    ),
    name="static",
)