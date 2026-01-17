import logging
import sys

import serial
from fastapi import HTTPException
from fastapi import Request
from loguru import logger

from api.schemas import grbl as grbl_schemas

def setup_loguru(level="INFO"):
    class PropagateHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            record.extra = []
            logging.getLogger(record.name).handle(record)

    logger.remove()
    logger.add(sink=sys.stdout, level=level)
    logger.add(PropagateHandler(), level=level, format="{message}")

def get_grbl_connection(request: Request) -> grbl_schemas.GrblConnection:
    """
    Get GRBL connection from application state.

    Args:
        request: FastAPI request object

    Returns:
        GRBL connection with cached settings

    Raises:
        HTTPException: 503 if GRBL connection is not available
    """
    if not hasattr(request.app.state, 'grbl_connection'):
        raise HTTPException(status_code=503, detail="GRBL connection not available")
    return request.app.state.grbl_connection

def get_limit_connection(request: Request) -> serial.Serial:
    """
    Get limit controller serial connection from application state.

    Args:
        request: FastAPI request object

    Returns:
        Limit controller serial connection

    Raises:
        HTTPException: 503 if limit connection is not available
    """
    if not hasattr(request.app.state, 'limit_connection'):
        raise HTTPException(status_code=503, detail="Limit controller connection not available")
    return request.app.state.limit_connection.serial
