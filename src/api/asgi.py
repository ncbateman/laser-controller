import fastapi
from contextlib import asynccontextmanager
from loguru import logger

from api.modules import grbl
from api.modules import limits
from api.routers.calibration import factory as calibration_factory
from api.routers.health import factory as health_factory
from api.routers.jog import factory as jog_factory
from api import utils

@asynccontextmanager
async def lifespan(app: fastapi.FastAPI):
    logger.info("Starting laser-controller-api")

    logger.info("Connecting to GRBL controller...")
    try:
        grbl_connection = grbl.create_grbl_connection()
        app.state.grbl_connection = grbl_connection
        logger.info(f"GRBL connection established on {grbl_connection.port}")
    except Exception as e:
        logger.error(f"Failed to connect to GRBL controller: {e}")
        raise

    logger.info("Connecting to limit controller...")
    try:
        limit_port = limits.find_limit_controller_port()
        if not limit_port:
            raise RuntimeError("Limit controller not found")
        limit_connection = limits.create_limit_controller_connection(limit_port)
        app.state.limit_connection = limit_connection
        logger.info(f"Limit controller connection established on {limit_port}")
    except Exception as e:
        logger.error(f"Failed to connect to limit controller: {e}")
        if hasattr(app.state, 'grbl_connection'):
            app.state.grbl_connection.close()
        raise

    yield

    logger.info("Shutting down laser-controller-api")

    if hasattr(app.state, 'limit_connection'):
        try:
            app.state.limit_connection.serial.close()
            logger.info("Limit controller connection closed")
        except Exception as e:
            logger.error(f"Error closing limit controller connection: {e}")

    if hasattr(app.state, 'grbl_connection'):
        try:
            app.state.grbl_connection.serial.close()
            logger.info("GRBL connection closed")
        except Exception as e:
            logger.error(f"Error closing GRBL connection: {e}")

def factory():
    utils.setup_loguru()

    app = fastapi.FastAPI(lifespan=lifespan)

    app.include_router(health_factory(app))
    app.include_router(calibration_factory(app))
    app.include_router(jog_factory(app))

    return app
