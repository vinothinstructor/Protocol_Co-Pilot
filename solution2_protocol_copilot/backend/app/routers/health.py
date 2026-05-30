from fastapi import APIRouter
from app.config import settings
from app.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="ok", llm_mode=settings.llm_mode.value)
