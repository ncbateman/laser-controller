import logging
import sys

from loguru import logger

def setup_loguru(level="INFO"):
    class PropagateHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            record.extra = []
            logging.getLogger(record.name).handle(record)

    logger.remove()
    logger.add(sink=sys.stdout, level=level)
    logger.add(PropagateHandler(), level=level, format="{message}")
