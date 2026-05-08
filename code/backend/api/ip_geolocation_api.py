"""IP geolocation API router that bridges API layer to IP geolocation app layer."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
import json
from typing import Annotated, Any, cast

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import PlainTextResponse, Response

from apps.ip_geolocation import (
    force_ipinfo_gz_update,
    get_ip_geolocation_load_status,
    lookup_client_asn_geolocation,
    lookup_client_country_geolocation,
    lookup_client_ip_geolocation,
    resolve_client_ip_address,
    lookup_ip_geolocation_by_request,
)
from models.admin_token_auth import AdminTokenValidationResultModel
from models.ip_geolocation import IpGeolocationLookupRequestModel
from services.admin_token_auth import require_admin_token

router = APIRouter()
router_root = APIRouter()


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


@router.get("/client_ipinfo", tags=["ip-geolocation"])
def get_client_ip_info_api(http_request: Request) -> dict[str, str | None]:
    """Return request client IP geolocation info as JSON payload under /api."""
    x_forwarded_for = http_request.headers.get("x-forwarded-for")
    client_host = http_request.client.host if http_request.client is not None else None
    lookup = lookup_client_ip_geolocation(x_forwarded_for=x_forwarded_for, client_host=client_host)

    if lookup.status == "failure":
        client_ip = resolve_client_ip_address(x_forwarded_for=x_forwarded_for, client_host=client_host)
        return {
            "ip": client_ip,
            "network": None,
            "country": None,
            "country_code": None,
            "continent": None,
            "continent_code": None,
            "asn": None,
            "as_domain": None,
        }

    return {
        "ip": getattr(lookup.data, "ip", None),
        "network": getattr(lookup.data, "network", None),
        "country": getattr(lookup.data, "country", None),
        "country_code": getattr(lookup.data, "country_code", None),
        "continent": getattr(lookup.data, "continent", None),
        "continent_code": getattr(lookup.data, "continent_code", None),
        "asn": getattr(lookup.data, "asn", None),
        "as_domain": getattr(lookup.data, "as_domain", None),
    }


@router.post("/ipinfo_update", tags=["ip-geolocation"])
def force_ipinfo_update(
    _auth: Annotated[AdminTokenValidationResultModel, Depends(require_admin_token)],
) -> dict[str, Any]:
    """Force one immediate IPinfo .gz downloader execution cycle."""
    return _to_payload(force_ipinfo_gz_update())


@router_root.get("/ip", tags=["ip-geolocation"], response_class=PlainTextResponse)
def get_client_ip(http_request: Request) -> PlainTextResponse:
    """Return request client IP address as a single-line plain-text response."""
    x_forwarded_for = http_request.headers.get("x-forwarded-for")
    client_host = http_request.client.host if http_request.client is not None else None
    client_ip = resolve_client_ip_address(x_forwarded_for=x_forwarded_for, client_host=client_host)
    return PlainTextResponse(content=f"{client_ip}\n")


@router_root.get("/", tags=["ip-geolocation"])
def get_client_ip_info(http_request: Request) -> Response:
    """Return client IP geolocation info as JSON payload at root path."""
    x_forwarded_for = http_request.headers.get("x-forwarded-for")
    client_host = http_request.client.host if http_request.client is not None else None
    lookup = lookup_client_ip_geolocation(x_forwarded_for=x_forwarded_for, client_host=client_host)

    if lookup.status == "failure":
        client_ip = resolve_client_ip_address(x_forwarded_for=x_forwarded_for, client_host=client_host)
        payload: dict[str, str | None] = {
            "ip": client_ip,
            "network": None,
            "country": None,
            "country_code": None,
            "continent": None,
            "continent_code": None,
            "asn": None,
            "as_name": None,
            "as_domain": None,
        }
    else:
        payload = {
            "ip": getattr(lookup.data, "ip", None),
            "network": getattr(lookup.data, "network", None),
            "country": getattr(lookup.data, "country", None),
            "country_code": getattr(lookup.data, "country_code", None),
            "continent": getattr(lookup.data, "continent", None),
            "continent_code": getattr(lookup.data, "continent_code", None),
            "asn": getattr(lookup.data, "asn", None),
            "as_name": getattr(lookup.data, "as_name", None),
            "as_domain": getattr(lookup.data, "as_domain", None),
        }

    pretty_json = json.dumps(payload, indent=2, ensure_ascii=False)
    return Response(content=f"{pretty_json}\n", media_type="application/json")


@router_root.get("/asn", tags=["ip-geolocation"], response_class=PlainTextResponse)
def get_client_asn(http_request: Request) -> PlainTextResponse:
    """Return ASN for request client IP as a single-line plain-text response."""
    x_forwarded_for = http_request.headers.get("x-forwarded-for")
    client_host = http_request.client.host if http_request.client is not None else None
    lookup = lookup_client_asn_geolocation(x_forwarded_for=x_forwarded_for, client_host=client_host)

    if lookup.status == "failure":
        return PlainTextResponse(content="failed\n")

    data_asn = getattr(lookup.data, "asn", None)
    if isinstance(data_asn, str) and data_asn.strip():
        return PlainTextResponse(content=f"{data_asn}\n")

    return PlainTextResponse(content=f"{lookup.resolution_state}\n")


@router_root.get("/country", tags=["ip-geolocation"], response_class=PlainTextResponse)
def get_client_country(http_request: Request) -> PlainTextResponse:
    """Return country code for request client IP as a single-line plain-text response."""
    x_forwarded_for = http_request.headers.get("x-forwarded-for")
    client_host = http_request.client.host if http_request.client is not None else None
    lookup = lookup_client_country_geolocation(x_forwarded_for=x_forwarded_for, client_host=client_host)

    if lookup.status == "failure":
        return PlainTextResponse(content="failed\n")

    data_country = getattr(lookup.data, "country", None)
    if isinstance(data_country, str) and data_country.strip():
        return PlainTextResponse(content=f"{data_country}\n")

    return PlainTextResponse(content=f"{lookup.resolution_state}\n")
