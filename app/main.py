import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.webhook import router as webhook_router
from app.config import settings
from app.db import engine

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("chibot")


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("ChiBot starting (env=%s)", settings.env)
    yield
    await engine.dispose()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.include_router(webhook_router)


@app.get("/healthz", tags=["ops"])
async def healthz() -> JSONResponse:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return JSONResponse({"status": "ok", "database": "ok"})
    except Exception:
        logger.exception("health check: database unreachable")
        return JSONResponse(
            {"status": "degraded", "database": "error"}, status_code=503
        )