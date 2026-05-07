"""Unit tests for IP geolocation app orchestration."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest
from fastapi import HTTPException


BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from apps.ip_geolocation import (  # noqa: E402
    get_ip_geolocation_load_status,
    lookup_asn_geolocation,
    lookup_ip_geolocation,
    lookup_ip_geolocation_by_request,
)
from models.ip_geolocation import (  # noqa: E402
    IpGeolocationAsnLookupDataModel,
    IpGeolocationAsnSubnetItemModel,
    IpGeolocationLookupDataModel,
    IpGeolocationLookupRequestModel,
    IpGeolocationLookupSuccessResponseModel,
)


def test_lookup_ip_geolocation_calls_service_and_returns_payload(monkeypatch) -> None:
    """App lookup should delegate to service and return service response unchanged."""
    expected = IpGeolocationLookupSuccessResponseModel(
        status="success",
        service_state="ready",
        resolution_state="not_found",
        data=IpGeolocationLookupDataModel(
            ip="9.9.9.9",
            network=None,
            country=None,
            country_code=None,
            continent=None,
            continent_code=None,
            asn=None,
            as_name=None,
            as_domain=None,
        ),
    )
    captured: dict[str, object] = {}

    def _fake_lookup(self, ip: str):
        captured["ip"] = ip
        return expected

    monkeypatch.setattr(
        "services.ip_geolocation.ip_geolocation_service.IpGeolocationService.lookup_ip_geolocation",
        _fake_lookup,
    )

    payload = lookup_ip_geolocation("9.9.9.9")

    assert payload is expected
    assert captured == {"ip": "9.9.9.9"}


def test_get_ip_geolocation_load_status_calls_service(monkeypatch) -> None:
    """App status should delegate to service and return status contract."""
    from models.ip_geolocation import IpGeolocationLoadCountersModel, IpGeolocationLoadStatusModel

    expected = IpGeolocationLoadStatusModel(
        service_state="loading",
        counters=IpGeolocationLoadCountersModel(total=10, loaded=2, malformed=1),
    )

    def _fake_status(self):
        return expected

    monkeypatch.setattr(
        "services.ip_geolocation.ip_geolocation_service.IpGeolocationService.get_ip_geolocation_load_status",
        _fake_status,
    )

    payload = get_ip_geolocation_load_status()
    assert payload is expected


def test_lookup_ip_geolocation_by_request_dispatches_ip_type(monkeypatch) -> None:
    """Request-based lookup should route ip type to ip lookup handler."""
    expected = IpGeolocationLookupSuccessResponseModel(
        status="success",
        service_state="ready",
        resolution_state="not_found",
        data=IpGeolocationLookupDataModel(
            ip="8.8.8.8",
            network=None,
            country=None,
            country_code=None,
            continent=None,
            continent_code=None,
            asn=None,
            as_name=None,
            as_domain=None,
        ),
    )

    def _fake_lookup(ip: str):
        assert ip == "8.8.8.8"
        return expected

    monkeypatch.setattr("apps.ip_geolocation.ip_geolocation_app.lookup_ip_geolocation", _fake_lookup)

    payload = lookup_ip_geolocation_by_request(
        IpGeolocationLookupRequestModel(type="ip", value="8.8.8.8")
    )

    assert payload is expected


def test_lookup_asn_geolocation_calls_service_and_returns_payload(monkeypatch) -> None:
    """App ASN lookup should delegate to service and return service response unchanged."""
    expected = IpGeolocationLookupSuccessResponseModel(
        status="success",
        service_state="ready",
        resolution_state="found",
        data=IpGeolocationAsnLookupDataModel(
            asn="AS13335",
            items=(
                IpGeolocationAsnSubnetItemModel(
                    network="1.1.1.0/24",
                    country="Australia",
                    country_code="AU",
                    continent="Oceania",
                    continent_code="OC",
                ),
            ),
            total=1,
        ),
    )
    captured: dict[str, object] = {}

    def _fake_lookup(self, asn: str):
        captured["asn"] = asn
        return expected

    monkeypatch.setattr(
        "services.ip_geolocation.ip_geolocation_service.IpGeolocationService.lookup_asn_geolocation",
        _fake_lookup,
    )

    payload = lookup_asn_geolocation("AS13335")

    assert payload is expected
    assert captured == {"asn": "AS13335"}


def test_lookup_ip_geolocation_by_request_dispatches_asn_type(monkeypatch) -> None:
    """Request-based lookup should route asn type to asn lookup handler."""
    expected = IpGeolocationLookupSuccessResponseModel(
        status="success",
        service_state="ready",
        resolution_state="found",
        data=IpGeolocationAsnLookupDataModel(
            asn="AS15169",
            items=(
                IpGeolocationAsnSubnetItemModel(
                    network="8.8.8.0/24",
                    country="United States",
                    country_code="US",
                    continent="North America",
                    continent_code="NA",
                ),
            ),
            total=1,
        ),
    )

    def _fake_lookup(asn: str):
        assert asn == "AS15169"
        return expected

    monkeypatch.setattr("apps.ip_geolocation.ip_geolocation_app.lookup_asn_geolocation", _fake_lookup)

    payload = lookup_ip_geolocation_by_request(
        IpGeolocationLookupRequestModel(type="asn", value="AS15169")
    )

    assert payload is expected


def test_lookup_ip_geolocation_by_request_rejects_unsupported_type() -> None:
    """Request-based lookup should raise client error for unsupported types."""
    with pytest.raises(HTTPException) as exc_info:
        lookup_ip_geolocation_by_request(
            IpGeolocationLookupRequestModel(type="country", value="US")
        )

    assert exc_info.value.status_code == 400
    assert "Unsupported lookup type 'country'" in str(exc_info.value)
