"""Root-level API router (non-/api paths) for BGPX backend."""

from fastapi import APIRouter

from .ip_geolocation_api import router_root as ip_geolocation_root_router

router = APIRouter()

router.include_router(ip_geolocation_root_router)
