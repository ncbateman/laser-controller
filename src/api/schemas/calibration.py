import pydantic

class CalibrationRequest(pydantic.BaseModel):
    outline: bool = True

class CalibrationResponse(pydantic.BaseModel):
    status: str
    message: str
    x_axis_length: float | None = None
    y_axis_length: float | None = None

class AxisCalibrationResponse(pydantic.BaseModel):
    status: str
    message: str
    axis: str
    measured_length: float | None = None
    known_length: float | None = None
    steps_per_mm: float | None = None
