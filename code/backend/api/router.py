"""Main API router for the BGPX backend."""

from fastapi import APIRouter
from .health_api import router as health_router
from .ping_api import router as ping_router
from .traceroute_api import router as traceroute_router

router = APIRouter()

router.include_router(health_router)
router.include_router(ping_router)
router.include_router(traceroute_router)
