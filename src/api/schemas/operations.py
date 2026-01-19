import pydantic

class SvgToGcodeRequest(pydantic.BaseModel):
    feed: int = pydantic.Field(5000, description="Feed rate in mm/min for cutting movements")
    movement_feed: int = pydantic.Field(10000, description="Feed rate in mm/min for rapid movements")
    origin_x: float = pydantic.Field(0.0, description="X coordinate offset in mm from home position")
    origin_y: float = pydantic.Field(0.0, description="Y coordinate offset in mm from home position")

class SvgToGcodeResponse(pydantic.BaseModel):
    status: str
    message: str
    commands_sent: int
    final_position_x: float | None = None
    final_position_y: float | None = None
    final_position_z: float | None = None
