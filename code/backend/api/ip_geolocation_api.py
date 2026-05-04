"""IP geolocation API router that bridges API layer to IP geolocation app layer."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, cast

from fastapi import APIRouter

from apps.ip_geolocation import get_ip_geolocation_load_status, lookup_ip_geolocation

router = APIRouter()


def _to_payload(model: object) -> dict[str, Any]:
    """Convert dataclass-based service/app models to JSON-serializable dictionaries."""
    if is_dataclass(model) and not isinstance(model, type):
        return asdict(cast(Any, model))

    raise TypeError("IP geolocation API expected dataclass response model")


@router.get("/geo/lookup", tags=["ip-geolocation"])
def lookup_ip_geo(ip: str) -> dict[str, Any]:
    """Lookup requested IP geolocation using app/service contract."""
    return _to_payload(lookup_ip_geolocation(ip))


@router.get("/geo/status", tags=["ip-geolocation"])
def get_ip_geo_status() -> dict[str, Any]:
    """Return current IP geolocation service load/refresh status."""
    return _to_payload(get_ip_geolocation_load_status())
