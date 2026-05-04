"""Unit tests for Stage 5 IP geolocation service facade behavior."""

from __future__ import annotations

from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from infra.ip_geolocation import IpGeolocationReadResult
from models.ip_geolocation import IpGeolocationLookupFailureResponseModel
from services.ip_geolocation import IpGeolocationService
from services.ip_geolocation.ip_geolocation_data_refresher import SourceFingerprint


def _sample_read_result() -> IpGeolocationReadResult:
    from models.ip_geolocation import IpGeolocationRecordModel

    return IpGeolocationReadResult(
        records=[
            IpGeolocationRecordModel(
                network="8.8.8.0/24",
                country="United States",
                country_code="US",
                continent="North America",
                continent_code="NA",
                asn="AS15169",
                as_name="Google LLC",
                as_domain="google.com",
            )
        ],
        total_lines=2,
        malformed_lines=1,
    )


def test_lookup_unresolved_while_loading_returns_initializing_db() -> None:
    """Unresolved lookup during loading should map to initializing_db."""
    service = IpGeolocationService()

    payload = service.lookup_ip_geolocation("1.1.1.1")

    assert payload.status == "success"
    assert payload.service_state == "loading"
    assert payload.resolution_state == "initializing_db"


def test_publish_transitions_service_to_ready_and_updates_status_counters() -> None:
    """First publish should atomically swap snapshot and mark service ready."""
    service = IpGeolocationService()

    service.publish_snapshot(
        _sample_read_result(),
        {
            "source_fingerprint": SourceFingerprint(inode=777, mtime_ns=888),
            "refresh_attempt_count": 4,
            "refresh_success_count": 3,
            "refresh_failure_count": 1,
        },
    )

    status = service.get_ip_geolocation_load_status()

    assert status.service_state == "ready"
    assert status.counters.total == 2
    assert status.counters.loaded == 1
    assert status.counters.malformed == 1
    assert status.refresh is not None
    assert status.refresh.active_source_fingerprint is not None
    assert status.refresh.active_source_fingerprint.inode == 777
    assert status.refresh.active_source_fingerprint.mtime_ns == 888
    assert status.refresh.refresh_attempt_count == 4
    assert status.refresh.refresh_success_count == 3
    assert status.refresh.refresh_failure_count == 1


def test_lookup_found_after_publish_returns_found_with_geo_payload() -> None:
    """Matched lookup should return found and mapped geo payload data."""
    service = IpGeolocationService()
    service.publish_snapshot(_sample_read_result(), {})

    payload = service.lookup_ip_geolocation("8.8.8.8")

    assert payload.status == "success"
    assert payload.service_state == "ready"
    assert payload.resolution_state == "found"
    assert payload.data.network == "8.8.8.0/24"
    assert payload.data.country_code == "US"
    assert payload.data.asn == "AS15169"


def test_lookup_unresolved_after_ready_returns_not_found() -> None:
    """Unresolved lookup after readiness should map to not_found."""
    service = IpGeolocationService()
    service.publish_snapshot(_sample_read_result(), {})

    payload = service.lookup_ip_geolocation("9.9.9.9")

    assert payload.status == "success"
    assert payload.service_state == "ready"
    assert payload.resolution_state == "not_found"


def test_failed_state_returns_failure_envelope() -> None:
    """Service failed state should return standard failure envelope."""
    service = IpGeolocationService()
    service._service_state = "failed"  # explicit state simulation for unit test

    payload = service.lookup_ip_geolocation("8.8.8.8")

    assert isinstance(payload, IpGeolocationLookupFailureResponseModel)
    assert payload.status == "failure"
    assert payload.service_state == "failed"
    assert payload.error.code == "IP_GEO_SERVICE_FAILED"
