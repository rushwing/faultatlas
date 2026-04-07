import json
import logging
from collections.abc import Callable

from confluent_kafka import Consumer as ConfluentConsumer
from confluent_kafka import KafkaError, KafkaException

logger = logging.getLogger(__name__)


class KafkaConsumer:
    def __init__(self, bootstrap_servers: str, group_id: str, topics: list[str]) -> None:
        self._consumer = ConfluentConsumer(
            {
                "bootstrap.servers": bootstrap_servers,
                "group.id": group_id,
                "auto.offset.reset": "earliest",
                "enable.auto.commit": False,
            }
        )
        self._consumer.subscribe(topics)
        self._running = False

    def run(self, handler: Callable[[str, dict], None], poll_timeout: float = 1.0) -> None:
        self._running = True
        logger.info("kafka consumer started", extra={"topics": self._consumer.assignment()})
        try:
            while self._running:
                msg = self._consumer.poll(poll_timeout)
                if msg is None:
                    continue
                if msg.error():
                    err = msg.error()
                    if err.code() == KafkaError._PARTITION_EOF:  # type: ignore[union-attr]
                        continue
                    raise KafkaException(err)
                try:
                    payload = json.loads(msg.value().decode("utf-8"))  # type: ignore[union-attr]
                    handler(msg.topic(), payload)  # type: ignore[arg-type]
                    self._consumer.commit(message=msg)
                except Exception:
                    logger.exception("handler failed", extra={"topic": msg.topic()})
        finally:
            self._consumer.close()

    def stop(self) -> None:
        self._running = False
