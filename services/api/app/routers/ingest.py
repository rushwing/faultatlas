import hashlib
import uuid
import logging
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel

from faultatlas.events.document_events import DocumentUploaded
from faultatlas.kafka.topics import Topics
from faultatlas.mongo.client import Collections
from faultatlas.redis.client import RedisKeys

from ..dependencies import AuthDep, DBDep, RedisDep, KafkaDep

logger = logging.getLogger(__name__)
router = APIRouter()


class IngestResponse(BaseModel):
    document_id: str
    status: str
    message: str


@router.post("", response_model=IngestResponse)
async def upload_document(
    _: AuthDep,
    db: DBDep,
    redis: RedisDep,
    kafka: KafkaDep,
    file: UploadFile = File(...),
) -> IngestResponse:
    content = await file.read()
    doc_hash = hashlib.sha256(content).hexdigest()

    # Idempotency check
    idempotency_key = RedisKeys.idempotency(doc_hash)
    if await redis.get(idempotency_key):
        raise HTTPException(status_code=409, detail="Document already submitted")

    document_id = str(uuid.uuid4())
    correlation_id = str(uuid.uuid4())
    storage_path = f"uploads/{document_id}/{file.filename}"

    # Persist document record
    await db[Collections.DOCUMENTS].insert_one({
        "_id": document_id,
        "filename": file.filename,
        "content_type": file.content_type,
        "status": "pending",
        "source_metadata": {"size_bytes": len(content)},
        "correlation_id": correlation_id,
    })

    # Set idempotency key (24h TTL)
    await redis.setex(idempotency_key, 86400, "processing")
    await redis.setex(RedisKeys.doc_status(document_id), 3600, "pending")

    # Publish event
    event = DocumentUploaded(
        document_id=document_id,
        filename=file.filename or "unknown",
        content_type=file.content_type or "application/octet-stream",
        storage_path=storage_path,
        correlation_id=correlation_id,
    )
    kafka.publish(Topics.DOCUMENTS_UPLOADED, event, key=document_id)

    logger.info("document uploaded", extra={"document_id": document_id, "filename": file.filename})
    return IngestResponse(document_id=document_id, status="pending", message="Ingestion started")


@router.get("/{document_id}/status")
async def get_document_status(document_id: str, _: AuthDep, redis: RedisDep) -> dict:
    status = await redis.get(RedisKeys.doc_status(document_id))
    return {"document_id": document_id, "status": status or "unknown"}
