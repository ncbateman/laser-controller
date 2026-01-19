import time

import fastapi
from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from loguru import logger

from api.modules import grbl
from api.schemas import grbl as grbl_schemas
from api.schemas.jog import JogRequest
from api.schemas.jog import JogResponse
from api.schemas.jog import ReturnToHomeRequest
from api import utils

async def jog_endpoint(
    request: JogRequest,
    grbl_connection: grbl_schemas.GrblConnection = Depends(utils.get_grbl_connection)
) -> JogResponse:
    """
    Jog the toolhead by a specified distance in X and/or Y directions.
    GRBL will enforce soft limits automatically. Negative values move backward, positive values move forward.

    Args:
        request: JogRequest containing x and/or y distances in mm (can be negative), and optional feed rate
        grbl_connection: GRBL connection with cached settings

    Returns:
        JogResponse with status and new position after jog

    Raises:
        HTTPException: 400 if no axis specified or GRBL rejects movement (e.g., soft limit exceeded), 500 if jog fails
    """
    if request.x is None and request.y is None:
        raise HTTPException(status_code=400, detail="At least one axis (x or y) must be specified")

    grbl_ser = grbl_connection.serial

    try:
        current_pos = grbl.query_position(grbl_ser)
        if current_pos.x is None or current_pos.y is None:
            raise HTTPException(status_code=500, detail="Unable to query current work position")

        grbl.set_mode_relative(grbl_ser)
        grbl.move_relative(grbl_ser, x=request.x, y=request.y, feed=request.feed, invert_y=True)

        max_distance = max(
            abs(request.x) if request.x is not None else 0,
            abs(request.y) if request.y is not None else 0
        )
        move_time = (max_distance / request.feed) * 60.0 + 0.5
        time.sleep(move_time)
        grbl_ser.read_all()

        final_pos = grbl.query_position(grbl_ser)

        return JogResponse(
            status="success",
            message="Jog completed successfully",
            new_position_x=final_pos.x,
            new_position_y=final_pos.y,
            new_position_z=final_pos.z
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Jog failed: {str(e)}")

async def return_to_home_endpoint(
    request: ReturnToHomeRequest,
    grbl_connection: grbl_schemas.GrblConnection = Depends(utils.get_grbl_connection)
) -> JogResponse:
    """
    Return toolhead to home position (work coordinate 0,0,0).
    Home position is the front-left corner + 10mm offset as set during calibration.

    Args:
        request: ReturnToHomeRequest containing optional feed rate
        grbl_connection: GRBL connection with cached settings

    Returns:
        JogResponse with status and position after returning home

    Raises:
        HTTPException: 400 if GRBL rejects movement, 500 if return to home fails
    """
    grbl_ser = grbl_connection.serial

    try:
        current_pos = grbl.query_position(grbl_ser)
        if current_pos.x is None or current_pos.y is None:
            raise HTTPException(status_code=500, detail="Unable to query current work position")

        grbl.set_mode_absolute(grbl_ser)
        grbl.move_absolute(grbl_ser, x=0, y=0, feed=request.feed, invert_y=False)

        max_distance = max(abs(current_pos.x), abs(current_pos.y))
        move_time = (max_distance / request.feed) * 60.0 + 0.5
        time.sleep(move_time)
        grbl_ser.read_all()

        final_pos = grbl.query_position(grbl_ser)

        return JogResponse(
            status="success",
            message="Returned to home successfully",
            new_position_x=final_pos.x,
            new_position_y=final_pos.y,
            new_position_z=final_pos.z
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Return to home failed: {str(e)}")

def factory(app: fastapi.FastAPI) -> APIRouter:
    """
    Create and configure the jog API router with jogging endpoints.

    Args:
        app: FastAPI application instance

    Returns:
        Configured APIRouter with jog endpoints:
        - POST /jog - Jog toolhead by specified distances in X and/or Y directions
        - POST /jog/home - Return toolhead to home position (0,0,0)
    """
    router = APIRouter(prefix="/jog", tags=["jog"])

    router.add_api_route(
        "/",
        jog_endpoint,
        methods=["POST"],
        response_model=JogResponse
    )

    router.add_api_route(
        "/home",
        return_to_home_endpoint,
        methods=["POST"],
        response_model=JogResponse
    )

    return router
