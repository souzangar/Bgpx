"""IP geolocation API router that bridges API layer to IP geolocation app layer."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Annotated, Any, cast

from fastapi import APIRouter, Body, Depends

from apps.ip_geolocation import (
    force_ipinfo_gz_update,
    get_ip_geolocation_load_status,
    lookup_ip_geolocation_by_request,
)
from models.admin_token_auth import AdminTokenValidationResultModel
from models.ip_geolocation import IpGeolocationLookupRequestModel
from services.admin_token_auth import require_admin_token

router = APIRouter()


def _to_payload(model: object) -> dict[str, Any]:
    """Convert dataclass-based service/app models to JSON-serializable dictionaries."""
    if is_dataclass(model) and not isinstance(model, type):
        return asdict(cast(Any, model))

    raise TypeError("IP geolocation API expected dataclass response model")


@router.get("/ipinfo", tags=["ip-geolocation"])
def lookup_ip_geo(
    request: Annotated[IpGeolocationLookupRequestModel, Body(...)],
) -> dict[str, Any]:
    """Lookup requested geolocation using typed request body (GET-with-body contract)."""
    return _to_payload(lookup_ip_geolocation_by_request(request))


@router.get("/ipinfo_status", tags=["ip-geolocation"])
def get_ip_geo_status() -> dict[str, Any]:
    """Return current IP geolocation service load/refresh status."""
    return _to_payload(get_ip_geolocation_load_status())


@router.post("/ipinfo_update", tags=["ip-geolocation"])
def force_ipinfo_update(
    _auth: Annotated[AdminTokenValidationResultModel, Depends(require_admin_token)],
) -> dict[str, Any]:
    """Force one immediate IPinfo .gz downloader execution cycle."""
    return _to_payload(force_ipinfo_gz_update())
