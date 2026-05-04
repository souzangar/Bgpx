"""Unit tests for IP geolocation app orchestration."""

from __future__ import annotations

from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from apps.ip_geolocation import (  # noqa: E402
    get_ip_geolocation_load_status,
    lookup_ip_geolocation,
)
from models.ip_geolocation import IpGeolocationLookupDataModel, IpGeolocationLookupSuccessResponseModel  # noqa: E402


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
