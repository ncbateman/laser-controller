import serial

import fastapi
from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException

from api.schemas.calibration import AxisCalibrationResponse
from api.schemas.calibration import CalibrationRequest
from api.schemas.calibration import CalibrationResponse
from api.schemas.calibration import StepsPerMmRequest
from api.schemas.calibration import StepsPerMmResponse
from api.schemas import grbl as grbl_schemas
from api.services import calibration
from api import utils

async def home_all_endpoint(
    request: CalibrationRequest,
    grbl_connection: grbl_schemas.GrblConnection = Depends(utils.get_grbl_connection),
    limit_ser: serial.Serial = Depends(utils.get_limit_connection)
) -> CalibrationResponse:
    """
    Run full calibration sequence: Y axis first, then X axis.
    Sets center as origin (0,0,0) after calibration.
    Optionally outlines the workspace border.

    Args:
        request: CalibrationRequest containing outline option
        grbl_connection: GRBL connection with cached settings
        limit_ser: Limit controller serial connection

    Returns:
        CalibrationResponse with calibration status and axis lengths

    Raises:
        HTTPException: 500 if calibration fails, 503 if connections unavailable
    """
    try:
        result = calibration.home_all(grbl_connection, limit_ser, outline=request.outline)
        return CalibrationResponse(
            status=result["status"],
            message=result["message"],
            x_axis_length=result.get("x_axis_length"),
            y_axis_length=result.get("y_axis_length")
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def home_x_endpoint(
    grbl_connection: grbl_schemas.GrblConnection = Depends(utils.get_grbl_connection),
    limit_ser: serial.Serial = Depends(utils.get_limit_connection)
) -> AxisCalibrationResponse:
    """
    Calibrate X axis using two-pass homing with calibration.

    Args:
        grbl_connection: GRBL connection with cached settings
        limit_ser: Limit controller serial connection

    Returns:
        AxisCalibrationResponse with X axis calibration results

    Raises:
        HTTPException: 500 if calibration fails, 503 if connections unavailable
    """
    try:
        result = calibration.home_x_axis_fast(grbl_connection, limit_ser)
        return AxisCalibrationResponse(
            status=result["status"],
            message="X axis calibration complete",
            axis=result["axis"],
            measured_length=result.get("measured_length"),
            known_length=291.0,
            steps_per_mm=result.get("steps_per_mm")
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def home_y_endpoint(
    grbl_connection: grbl_schemas.GrblConnection = Depends(utils.get_grbl_connection),
    limit_ser: serial.Serial = Depends(utils.get_limit_connection)
) -> AxisCalibrationResponse:
    """
    Calibrate Y axis using two-pass homing with calibration.
    Moves both Y and Z together (dual motor Y axis).

    Args:
        grbl_connection: GRBL connection with cached settings
        limit_ser: Limit controller serial connection

    Returns:
        AxisCalibrationResponse with Y axis calibration results

    Raises:
        HTTPException: 500 if calibration fails, 503 if connections unavailable
    """
    try:
        result = calibration.home_y_axis_fast(grbl_connection, limit_ser)
        return AxisCalibrationResponse(
            status=result["status"],
            message="Y axis calibration complete",
            axis=result["axis"],
            measured_length=result.get("measured_length"),
            known_length=899.0,
            steps_per_mm=result.get("steps_per_mm")
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def update_steps_per_mm_endpoint(
    request: StepsPerMmRequest,
    grbl_connection: grbl_schemas.GrblConnection = Depends(utils.get_grbl_connection)
) -> StepsPerMmResponse:
    """
    Update GRBL steps per mm settings for specified axes.

    Args:
        request: StepsPerMmRequest containing x, y, and/or z values to update
        grbl_connection: GRBL connection with cached settings

    Returns:
        StepsPerMmResponse with updated steps per mm values

    Raises:
        HTTPException: 400 if no axes specified, 500 if update fails
    """
    if request.x is None and request.y is None and request.z is None:
        raise HTTPException(status_code=400, detail="At least one axis (x, y, or z) must be specified")

    try:
        if request.x is not None:
            grbl_connection.update_setting("x_steps_per_mm", request.x)
        if request.y is not None:
            grbl_connection.update_setting("y_steps_per_mm", request.y)
        if request.z is not None:
            grbl_connection.update_setting("z_steps_per_mm", request.z)

        return StepsPerMmResponse(
            status="success",
            message="Steps per mm updated successfully",
            x_steps_per_mm=grbl_connection.settings.x_steps_per_mm,
            y_steps_per_mm=grbl_connection.settings.y_steps_per_mm,
            z_steps_per_mm=grbl_connection.settings.z_steps_per_mm
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def factory(app: fastapi.FastAPI) -> APIRouter:
    """
    Create and configure the calibration API router with all calibration endpoints.

    Args:
        app: FastAPI application instance

    Returns:
        Configured APIRouter with calibration endpoints:
        - POST /calibration/home-all - Full calibration (Y then X)
        - POST /calibration/home-x - X axis calibration only
        - POST /calibration/home-y - Y axis calibration only
        - PUT /calibration/steps-per-mm - Update GRBL steps per mm settings
    """
    router = APIRouter(prefix="/calibration", tags=["calibration"])

    router.add_api_route(
        "/home-all",
        home_all_endpoint,
        methods=["POST"],
        response_model=CalibrationResponse
    )

    router.add_api_route(
        "/home-x",
        home_x_endpoint,
        methods=["POST"],
        response_model=AxisCalibrationResponse
    )

    router.add_api_route(
        "/home-y",
        home_y_endpoint,
        methods=["POST"],
        response_model=AxisCalibrationResponse
    )

    router.add_api_route(
        "/steps-per-mm",
        update_steps_per_mm_endpoint,
        methods=["PUT"],
        response_model=StepsPerMmResponse
    )

    return router
