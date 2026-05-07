"""IP geolocation app orchestration for higher-layer consumption."""

from __future__ import annotations

from fastapi import HTTPException

from models.ip_geolocation import (
    IpGeolocationLoadStatusModel,
    IpGeolocationLookupRequestModel,
    IpGeolocationLookupResponseModel,
)
from services.ip_geolocation import IpGeolocationService


_ip_geolocation_service = IpGeolocationService()


def get_ip_geolocation_service() -> IpGeolocationService:
    """Return process-local IP geolocation service instance used by app layer."""
    return _ip_geolocation_service


def lookup_ip_geolocation(ip: str) -> IpGeolocationLookupResponseModel:
    """Resolve a requested IP using service-layer lookup contract."""
    return get_ip_geolocation_service().lookup_ip_geolocation(ip)


def lookup_asn_geolocation(asn: str) -> IpGeolocationLookupResponseModel:
    """Resolve a requested ASN using service-layer lookup contract."""
    return get_ip_geolocation_service().lookup_asn_geolocation(asn)


def lookup_country_geolocation(country: str) -> IpGeolocationLookupResponseModel:
    """Resolve a requested country code using service-layer lookup contract."""
    return get_ip_geolocation_service().lookup_country_geolocation(country)


def lookup_continent_geolocation(continent: str) -> IpGeolocationLookupResponseModel:
    """Resolve a requested continent code using service-layer lookup contract."""
    return get_ip_geolocation_service().lookup_continent_geolocation(continent)


def lookup_ip_geolocation_by_request(
    request: IpGeolocationLookupRequestModel,
) -> IpGeolocationLookupResponseModel:
    """Dispatch lookup request by target type and delegate to service-backed handlers."""
    if request.type == "ip":
        return lookup_ip_geolocation(request.value)
    if request.type == "asn":
        return lookup_asn_geolocation(request.value)
    if request.type == "country":
        return lookup_country_geolocation(request.value)
    if request.type == "continent":
        return lookup_continent_geolocation(request.value)

    raise HTTPException(
        status_code=400,
        detail=(
            f"Unsupported lookup type '{request.type}'. "
            "Currently supported types: ['ip' (e.g., 8.8.8.8, 2a11:29c0:3d88:3849::1), 'asn' (e.g., AS13335), 'country' (e.g., IR), 'continent' (e.g., AS)]."
        ),
    )


def get_ip_geolocation_load_status() -> IpGeolocationLoadStatusModel:
    """Return current service load status for API/read consumers."""
    return get_ip_geolocation_service().get_ip_geolocation_load_status()
