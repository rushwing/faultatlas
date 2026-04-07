import asyncio
import logging
import signal
import sys

from faultatlas.kafka.consumer import KafkaConsumer
from faultatlas.kafka.producer import KafkaProducer
from faultatlas.kafka.topics import Topics
from faultatlas.mongo.client import close_client, get_database
from faultatlas.redis.client import get_redis

from .config import get_settings
from .consumers.document_upload import handle_document_uploaded

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","name":"%(name)s","message":"%(message)s"}',
)
logger = logging.getLogger(__name__)


async def run() -> None:
    settings = get_settings()
    db = get_database(settings.mongo_uri, settings.mongo_db)
    redis = get_redis(settings.redis_url)
    producer = KafkaProducer(settings.kafka_bootstrap_servers)

    def handler(topic: str, payload: dict) -> None:
        if topic == Topics.DOCUMENTS_UPLOADED:
            asyncio.get_event_loop().run_until_complete(
                handle_document_uploaded(payload, db, redis, producer, settings)
            )

    consumer = KafkaConsumer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=settings.kafka_consumer_group,
        topics=[Topics.DOCUMENTS_UPLOADED],
    )

    def shutdown(sig, frame):
        logger.info("shutting down ingestion worker")
        consumer.stop()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    logger.info("ingestion worker started")
    consumer.run(handler)
    await close_client()


if __name__ == "__main__":
    asyncio.run(run())
