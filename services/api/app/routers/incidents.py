import uuid
import logging
from datetime import datetime, UTC
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from faultatlas.mongo.client import Collections

from ..dependencies import AuthDep, DBDep

logger = logging.getLogger(__name__)
router = APIRouter()


class CreateIncidentRequest(BaseModel):
    title: str
    severity: str  # low | medium | high | critical
    related_document_ids: list[str] = []


class IncidentResponse(BaseModel):
    id: str
    title: str
    severity: str
    status: str
    created_at: datetime


@router.post("", response_model=IncidentResponse)
async def create_incident(request: CreateIncidentRequest, _: AuthDep, db: DBDep) -> IncidentResponse:
    incident_id = str(uuid.uuid4())
    now = datetime.now(UTC)
    doc = {
        "_id": incident_id,
        "title": request.title,
        "severity": request.severity,
        "status": "open",
        "created_at": now,
        "related_document_ids": request.related_document_ids,
        "timeline": [],
        "resolution": {},
    }
    await db[Collections.INCIDENTS].insert_one(doc)
    logger.info("incident created", extra={"incident_id": incident_id, "severity": request.severity})
    return IncidentResponse(id=incident_id, title=request.title, severity=request.severity, status="open", created_at=now)


@router.get("/{incident_id}", response_model=IncidentResponse)
async def get_incident(incident_id: str, _: AuthDep, db: DBDep) -> IncidentResponse:
    doc = await db[Collections.INCIDENTS].find_one({"_id": incident_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Incident not found")
    return IncidentResponse(
        id=doc["_id"],
        title=doc["title"],
        severity=doc["severity"],
        status=doc["status"],
        created_at=doc["created_at"],
    )


@router.get("")
async def list_incidents(_: AuthDep, db: DBDep) -> list[dict]:
    cursor = db[Collections.INCIDENTS].find({}, {"title": 1, "severity": 1, "status": 1, "created_at": 1})
    return [{"id": d["_id"], **{k: v for k, v in d.items() if k != "_id"}} async for d in cursor]
