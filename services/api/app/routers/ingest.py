import hashlib
import logging
import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile
from faultatlas.ingestion import ingest_document
from faultatlas.mongo.client import Collections
from faultatlas.redis.client import RedisKeys
from pydantic import BaseModel

from ..dependencies import AuthDep, DBDep, RedisDep, SettingsDep

logger = logging.getLogger(__name__)
router = APIRouter()


async def _clear_idempotency_if_not_persisted(
    db: DBDep,
    redis: RedisDep,
    *,
    idempotency_key: str,
    document_id: str,
) -> None:
    document = await db[Collections.DOCUMENTS].find_one({"_id": document_id}, {"_id": 1})
    if document is None:
        await redis.delete(idempotency_key)


class IngestResponse(BaseModel):
    document_id: str
    status: str
    message: str
    chunk_count: int = 0


@router.post("", response_model=IngestResponse)
async def upload_document(
    _: AuthDep,
    db: DBDep,
    redis: RedisDep,
    settings: SettingsDep,
    file: UploadFile = File(...),
) -> IngestResponse:
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File exceeds 50MB limit")

    doc_hash = hashlib.sha256(content).hexdigest()

    # Idempotency check
    idempotency_key = RedisKeys.idempotency(doc_hash)
    existing_document_id = await redis.get(idempotency_key)
    if existing_document_id:
        status = await redis.get(RedisKeys.doc_status(existing_document_id))
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Document already submitted",
                "document_id": existing_document_id,
                "status": status or "unknown",
            },
        )

    document_id = str(uuid.uuid4())
    await redis.setex(idempotency_key, 86400, document_id)
    try:
        result = await ingest_document(
            document_id=document_id,
            filename=file.filename or "unknown",
            content_type=file.content_type or "application/octet-stream",
            content=content,
            db=db,
            redis=redis,
            openai_api_key=settings.openai_api_key,
            embedding_model=settings.openai_embedding_model,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )
    except ValueError as exc:
        await _clear_idempotency_if_not_persisted(
            db,
            redis,
            idempotency_key=idempotency_key,
            document_id=document_id,
        )
        if str(exc) == "encrypted_pdf":
            raise HTTPException(status_code=500, detail="Document processing failed") from exc
        raise
    except RuntimeError as exc:
        await _clear_idempotency_if_not_persisted(
            db,
            redis,
            idempotency_key=idempotency_key,
            document_id=document_id,
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        await _clear_idempotency_if_not_persisted(
            db,
            redis,
            idempotency_key=idempotency_key,
            document_id=document_id,
        )
        raise HTTPException(status_code=500, detail="Document processing failed") from exc

    logger.info(
        "document indexed",
        extra={"document_id": document_id, "uploaded_filename": file.filename},
    )
    return IngestResponse(
        document_id=document_id,
        status=result["status"],
        message="Document indexed",
        chunk_count=result["chunk_count"],
    )


@router.get("/{document_id}/status")
async def get_document_status(document_id: str, _: AuthDep, db: DBDep, redis: RedisDep) -> dict:
    status = await redis.get(RedisKeys.doc_status(document_id))
    if status:
        return {"document_id": document_id, "status": status}

    document = await db[Collections.DOCUMENTS].find_one({"_id": document_id})
    if not document:
        return {"document_id": document_id, "status": "unknown"}

    payload = {"document_id": document_id, "status": document.get("status", "unknown")}
    if "error_detail" in document:
        payload["error_detail"] = document["error_detail"]
    return payload
