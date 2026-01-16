import pydantic

class HealthResponse(pydantic.BaseModel):
    status: str
