import fastapi
from fastapi import APIRouter

from api.schemas.health import HealthResponse

async def health_check() -> HealthResponse:
    return HealthResponse(status="ok")

def factory(app: fastapi.FastAPI) -> APIRouter:
    router = APIRouter()

    router.add_api_route(
        "/health/",
        health_check,
        methods=["GET"],
        response_model=HealthResponse,
        tags=["health"]
    )
    return router
