import logging
import sys

from pythonjsonlogger import jsonlogger


def setup_logging(log_level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(log_level.upper())
    # Quiet noisy libs
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
