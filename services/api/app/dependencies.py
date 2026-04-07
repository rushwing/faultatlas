from typing import Annotated
from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from motor.motor_asyncio import AsyncIOMotorDatabase
from redis.asyncio import Redis

from faultatlas.mongo.client import get_database
from faultatlas.redis.client import get_redis
from faultatlas.kafka.producer import KafkaProducer

from .config import Settings, get_settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(
    api_key: str | None = Security(api_key_header),
    settings: Settings = Depends(get_settings),
) -> str:
    if not api_key or api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return api_key


def get_db(settings: Settings = Depends(get_settings)) -> AsyncIOMotorDatabase:
    return get_database(settings.mongo_uri, settings.mongo_db)


def get_redis_client(settings: Settings = Depends(get_settings)) -> Redis:
    return get_redis(settings.redis_url)


def get_kafka_producer(settings: Settings = Depends(get_settings)) -> KafkaProducer:
    return KafkaProducer(settings.kafka_bootstrap_servers)


SettingsDep = Annotated[Settings, Depends(get_settings)]
DBDep = Annotated[AsyncIOMotorDatabase, Depends(get_db)]
RedisDep = Annotated[Redis, Depends(get_redis_client)]
KafkaDep = Annotated[KafkaProducer, Depends(get_kafka_producer)]
AuthDep = Annotated[str, Depends(verify_api_key)]
