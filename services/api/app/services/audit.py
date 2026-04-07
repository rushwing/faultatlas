import logging
import uuid
from datetime import datetime, UTC
from typing import Any
from motor.motor_asyncio import AsyncIOMotorDatabase

from faultatlas.mongo.client import Collections

logger = logging.getLogger(__name__)


async def write_audit(
    db: AsyncIOMotorDatabase,
    service: str,
    event_type: str,
    actor: str,
    resource_id: str,
    payload: dict[str, Any],
    correlation_id: str | None = None,
) -> None:
    await db[Collections.AUDIT_LOG].insert_one({
        "_id": str(uuid.uuid4()),
        "timestamp": datetime.now(UTC),
        "service": service,
        "event_type": event_type,
        "actor": actor,
        "resource_id": resource_id,
        "payload": payload,
        "correlation_id": correlation_id,
    })
