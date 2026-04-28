"""Health API router that bridges API layer to health app layer."""

from fastapi import APIRouter

from apps.health import router as health_app_router

router = APIRouter()

router.include_router(health_app_router)
