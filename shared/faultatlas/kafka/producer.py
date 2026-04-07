import logging

from confluent_kafka import Producer as ConfluentProducer
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class KafkaProducer:
    def __init__(self, bootstrap_servers: str) -> None:
        self._producer = ConfluentProducer({"bootstrap.servers": bootstrap_servers})

    def publish(self, topic: str, event: BaseModel, key: str | None = None) -> None:
        payload = event.model_dump_json().encode("utf-8")
        key_bytes = key.encode("utf-8") if key else None
        self._producer.produce(
            topic,
            value=payload,
            key=key_bytes,
            on_delivery=self._delivery_report,
        )
        self._producer.poll(0)

    def flush(self) -> None:
        self._producer.flush()

    @staticmethod
    def _delivery_report(err, msg) -> None:
        if err:
            logger.error("kafka delivery failed", extra={"topic": msg.topic(), "error": str(err)})
        else:
            logger.debug("kafka delivered", extra={"topic": msg.topic(), "offset": msg.offset()})
