import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .middleware.logging import setup_logging
from .routers import benchmark, diagnose, health, incidents, ingest, query

settings = get_settings()
setup_logging(settings.log_level)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="FaultAtlas API",
    description="AI Copilot for log analysis and intelligent incident handling",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.app_env == "development" else [],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, tags=["health"])
app.include_router(ingest.router, prefix="/documents", tags=["ingestion"])
app.include_router(diagnose.router, prefix="/diagnose", tags=["diagnosis"])
app.include_router(diagnose.debug_router, tags=["debug"])
app.include_router(query.router, prefix="/query", tags=["query"])
app.include_router(benchmark.router, prefix="/benchmark", tags=["benchmark"])
app.include_router(incidents.router, prefix="/incidents", tags=["incidents"])


@app.on_event("startup")
async def startup() -> None:
    logger.info("faultatlas api starting", extra={"env": settings.app_env})


@app.on_event("shutdown")
async def shutdown() -> None:
    from faultatlas.mongo.client import close_client

    await close_client()
    logger.info("faultatlas api shutdown complete")
