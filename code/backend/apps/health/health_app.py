"""Health app request router."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    """Return a basic health status for the backend service."""
    return {"status": "ok", "service": "bgpx-backend"}