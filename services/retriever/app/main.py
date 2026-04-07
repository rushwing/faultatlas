import logging
import sys

from fastapi import FastAPI

from .config import get_settings
from .routers import search

settings = get_settings()
logging.basicConfig(stream=sys.stdout, level=settings.log_level.upper())

app = FastAPI(
    title="FaultAtlas Retriever",
    description="Internal retrieval service — not public-facing",
    version="0.1.0",
    docs_url="/docs",
)

app.include_router(search.router, tags=["search"])


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "faultatlas-retriever"}


@app.on_event("shutdown")
async def shutdown() -> None:
    from faultatlas.mongo.client import close_client

    await close_client()
