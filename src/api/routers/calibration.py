import fastapi
from fastapi import APIRouter, HTTPException

from api.schemas.calibration import CalibrationRequest, CalibrationResponse, AxisCalibrationResponse
from api.services import calibration

def factory(app: fastapi.FastAPI) -> APIRouter:
    router = APIRouter(prefix="/calibration", tags=["calibration"])

    @router.post("/home-all", response_model=CalibrationResponse)
    async def home_all_endpoint(request: CalibrationRequest):
        """
        Run full calibration sequence: Y axis first, then X axis.
        Sets center as origin (0,0,0) after calibration.
        Optionally outlines the workspace border.
        """
        try:
            grbl_ser = app.state.grbl_connection.serial
            limit_ser = app.state.limit_connection.serial
            result = calibration.home_all(grbl_ser, limit_ser, outline=request.outline)
            return CalibrationResponse(
                status=result["status"],
                message=result["message"],
                x_axis_length=result.get("x_axis_length"),
                y_axis_length=result.get("y_axis_length")
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/home-x", response_model=AxisCalibrationResponse)
    async def home_x_endpoint():
        """
        Calibrate X axis using two-pass homing with calibration.
        """
        try:
            grbl_ser = app.state.grbl_connection.serial
            limit_ser = app.state.limit_connection.serial
            result = calibration.home_x_axis_fast(grbl_ser, limit_ser)
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

    @router.post("/home-y", response_model=AxisCalibrationResponse)
    async def home_y_endpoint():
        """
        Calibrate Y axis using two-pass homing with calibration.
        Moves both Y and Z together (dual motor Y axis).
        """
        try:
            grbl_ser = app.state.grbl_connection.serial
            limit_ser = app.state.limit_connection.serial
            result = calibration.home_y_axis_fast(grbl_ser, limit_ser)
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

    return router
