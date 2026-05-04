"""IP geolocation app orchestration for higher-layer consumption."""

from __future__ import annotations

from models.ip_geolocation import IpGeolocationLoadStatusModel, IpGeolocationLookupResponseModel
from services.ip_geolocation import IpGeolocationService


_ip_geolocation_service = IpGeolocationService()


def get_ip_geolocation_service() -> IpGeolocationService:
    """Return process-local IP geolocation service instance used by app layer."""
    return _ip_geolocation_service


def lookup_ip_geolocation(ip: str) -> IpGeolocationLookupResponseModel:
    """Resolve a requested IP using service-layer lookup contract."""
    return get_ip_geolocation_service().lookup_ip_geolocation(ip)


def get_ip_geolocation_load_status() -> IpGeolocationLoadStatusModel:
    """Return current service load status for API/read consumers."""
    return get_ip_geolocation_service().get_ip_geolocation_load_status()
