import serial

import pydantic

class LimitSwitch(pydantic.BaseModel):
    id: int
    state: int

class LimitControllerData(pydantic.BaseModel):
    device: str
    switches: list[LimitSwitch]

class LimitSwitchStateRequest(pydantic.BaseModel):
    switch_id: int
    timeout: float = 0.5

class LimitSwitchStateResponse(pydantic.BaseModel):
    switch_id: int
    state: int
    found: bool

class LimitControllerConnection(pydantic.BaseModel):
    port: str
    serial: serial.Serial

    model_config = {"arbitrary_types_allowed": True}
