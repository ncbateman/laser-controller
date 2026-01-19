import pydantic

class JogRequest(pydantic.BaseModel):
    x: float | None = pydantic.Field(None, description="X axis movement distance in mm (negative moves backward, positive moves forward)")
    y: float | None = pydantic.Field(None, description="Y axis movement distance in mm (negative moves backward, positive moves forward)")
    feed: int = pydantic.Field(5000, description="Feed rate in mm/min")

class JogResponse(pydantic.BaseModel):
    status: str
    message: str
    new_position_x: float | None = None
    new_position_y: float | None = None
    new_position_z: float | None = None

class ReturnToHomeRequest(pydantic.BaseModel):
    feed: int = pydantic.Field(5000, description="Feed rate in mm/min")
