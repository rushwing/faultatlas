import logging
import signal
import sys
import time

from faultatlas.mongo.client import close_client

from .config import get_settings

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","name":"%(name)s","message":"%(message)s"}',
)
logger = logging.getLogger(__name__)


def run() -> None:
    settings = get_settings()
    shutdown_requested = False

    def shutdown(sig, frame):
        nonlocal shutdown_requested
        logger.info("shutting down ingestion worker")
        shutdown_requested = True

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    logger.info(
        "ingestion worker is a Phase 2 stub in the current MVP",
        extra={"phase": "phase-1", "mode": settings.app_env},
    )
    try:
        while not shutdown_requested:
            time.sleep(1)
    finally:
        import asyncio

        asyncio.run(close_client())


if __name__ == "__main__":
    run()
