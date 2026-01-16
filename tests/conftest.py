import pytest
from unittest.mock import MagicMock

import fastapi
from fastapi.testclient import TestClient

from api import utils
from api.routers.calibration import factory as calibration_factory
from api.routers.health import factory as health_factory

@pytest.fixture
def app():
    utils.setup_loguru()

    app = fastapi.FastAPI()

    grbl_mock = MagicMock()
    grbl_mock.serial = MagicMock()
    grbl_mock.port = "/dev/ttyUSB1"

    limit_mock = MagicMock()
    limit_mock.serial = MagicMock()
    limit_mock.port = "/dev/ttyUSB0"

    app.state.grbl_connection = grbl_mock
    app.state.limit_connection = limit_mock

    app.include_router(health_factory(app))
    app.include_router(calibration_factory(app))

    return app

@pytest.fixture
def client(app: fastapi.FastAPI):
    return TestClient(app)
