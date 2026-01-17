import serial

import pydantic

class GrblCommandRequest(pydantic.BaseModel):
    command: str
    label: str
    retries: int = 3
    timeout: float = 2.0

class GrblCommandResponse(pydantic.BaseModel):
    success: bool
    response: str
    attempts: int

class GrblConnection(pydantic.BaseModel):
    port: str
    serial: serial.Serial
    settings: dict[int, float] = {}

    model_config = {"arbitrary_types_allowed": True}
