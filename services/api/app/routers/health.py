import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..dependencies import DBDep, RedisDep, SettingsDep

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    service: str = "faultatlas-api"


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/ready", response_model=HealthResponse)
async def ready(db: DBDep, redis: RedisDep, settings: SettingsDep) -> HealthResponse:
    try:
        await db.command("ping")
        await redis.execute_command("PING")
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{settings.retriever_url}/health")
        response.raise_for_status()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Service dependencies not ready") from exc
    return HealthResponse(status="ok")
