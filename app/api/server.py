import logging
from contextlib import asynccontextmanager
from multiprocessing.connection import Connection

from fastapi import FastAPI

from app.ipc.sender import PipeSender

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = app.state.pipe_connection
    app.state.pipe_sender = PipeSender(conn)
    logger.info("API: pipe sender connected")
    yield
    app.state.pipe_sender.close()
    logger.info("API: shutdown complete")


def create_app(pipe_connection: Connection) -> FastAPI:
    from app.api.routes_health import router as health_router
    from app.api.routes_scanner import router as scanner_router
    from app.api.routes_calendar import router as calendar_router

    app = FastAPI(
        title="Signal Processing Service",
        lifespan=lifespan,
    )
    app.state.pipe_connection = pipe_connection
    app.include_router(health_router)
    app.include_router(scanner_router)
    app.include_router(calendar_router)
    return app
