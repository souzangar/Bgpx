"""Unit tests for Stage 5 IP geolocation service facade behavior."""

from __future__ import annotations

from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from infra.ip_geolocation import IpGeolocationReadResult
from models.ip_geolocation import (
    IpGeolocationAsnLookupDataModel,
    IpGeolocationContinentLookupDataModel,
    IpGeolocationCountryLookupDataModel,
    IpGeolocationLookupDataModel,
    IpGeolocationLookupFailureResponseModel,
    IpGeolocationLookupSuccessResponseModel,
    IpGeolocationRecordModel,
)
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


def _record(network: str, as_name: str) -> IpGeolocationRecordModel:
    return IpGeolocationRecordModel(
        network=network,
        country="United States",
        country_code="US",
        continent="North America",
        continent_code="NA",
        asn="AS15169",
        as_name=as_name,
        as_domain="google.com",
    )


def _record_with_asn(network: str, asn: str) -> IpGeolocationRecordModel:
    return IpGeolocationRecordModel(
        network=network,
        country="United States",
        country_code="US",
        continent="North America",
        continent_code="NA",
        asn=asn,
        as_name="Provider",
        as_domain="provider.example",
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


def test_publish_non_final_chunk_keeps_service_loading_and_unresolved_lookup_initializing() -> None:
    """Non-final chunk publish should keep service in loading state."""
    service = IpGeolocationService()

    service.publish_snapshot(
        _sample_read_result(),
        {
            "is_final_chunk": False,
            "total_lines": 10,
            "malformed_lines": 2,
        },
    )

    status = service.get_ip_geolocation_load_status()
    assert status.service_state == "loading"
    assert status.counters.total == 10
    assert status.counters.loaded == 1
    assert status.counters.malformed == 2

    unresolved = service.lookup_ip_geolocation("9.9.9.9")
    assert unresolved.status == "success"
    assert unresolved.service_state == "loading"
    assert unresolved.resolution_state == "initializing_db"


def test_publish_non_final_chunk_exposes_staged_records_during_bootstrap() -> None:
    """Bootstrap load should progressively expose already-published chunks."""
    service = IpGeolocationService()

    service.publish_snapshot(
        _sample_read_result(),
        {
            "is_final_chunk": False,
            "total_lines": 10,
            "malformed_lines": 0,
        },
    )

    payload = service.lookup_ip_geolocation("8.8.8.8")
    assert payload.status == "success"
    assert payload.service_state == "loading"
    assert payload.resolution_state == "found"
    assert isinstance(payload.data, IpGeolocationLookupDataModel)
    assert payload.data.network == "8.8.8.0/24"


def test_publish_non_final_chunk_does_not_expose_staged_records_during_refresh() -> None:
    """Refresh load should keep old snapshot visible until final atomic swap."""
    service = IpGeolocationService()

    baseline = IpGeolocationReadResult(
        records=[
            _record("9.9.9.0/24", "Quad9"),
        ],
        total_lines=1,
        malformed_lines=0,
    )
    service.publish_snapshot(baseline, {})

    service.publish_snapshot(
        _sample_read_result(),
        {
            "is_final_chunk": False,
            "total_lines": 10,
            "malformed_lines": 0,
        },
    )

    old_payload = service.lookup_ip_geolocation("9.9.9.9")
    assert old_payload.status == "success"
    assert old_payload.service_state == "loading"
    assert old_payload.resolution_state == "found"
    assert isinstance(old_payload.data, IpGeolocationLookupDataModel)
    assert old_payload.data.network == "9.9.9.0/24"

    staged_payload = service.lookup_ip_geolocation("8.8.8.8")
    assert staged_payload.status == "success"
    assert staged_payload.service_state == "loading"
    assert staged_payload.resolution_state == "initializing_db"


def test_lookup_found_after_publish_returns_found_with_geo_payload() -> None:
    """Matched lookup should return found and mapped geo payload data."""
    service = IpGeolocationService()
    service.publish_snapshot(_sample_read_result(), {})

    payload = service.lookup_ip_geolocation("8.8.8.8")

    assert payload.status == "success"
    assert payload.service_state == "ready"
    assert payload.resolution_state == "found"
    assert isinstance(payload.data, IpGeolocationLookupDataModel)
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


def test_lookup_asn_found_after_publish_returns_found_with_geo_payload() -> None:
    """Matched ASN lookup should return all matched subnet records."""
    service = IpGeolocationService()
    service.publish_snapshot(
        IpGeolocationReadResult(
            records=[
                _record_with_asn("8.8.8.0/24", "AS15169"),
                _record_with_asn("8.8.4.0/24", "AS15169"),
                _record_with_asn("1.1.1.0/24", "AS13335"),
            ],
            total_lines=3,
            malformed_lines=0,
        ),
        {},
    )

    payload = service.lookup_asn_geolocation("as15169")

    assert payload.status == "success"
    assert payload.service_state == "ready"
    assert payload.resolution_state == "found"
    assert isinstance(payload.data, IpGeolocationAsnLookupDataModel)
    assert payload.data.asn == "AS15169"
    assert payload.data.total == 2
    assert len(payload.data.items) == 2
    assert payload.data.items[0].network == "8.8.8.0/24"
    assert payload.data.items[1].network == "8.8.4.0/24"


def test_lookup_asn_unresolved_while_loading_returns_initializing_db() -> None:
    """Unresolved ASN lookup during loading should map to initializing_db."""
    service = IpGeolocationService()

    payload = service.lookup_asn_geolocation("AS13335")

    assert payload.status == "success"
    assert payload.service_state == "loading"
    assert payload.resolution_state == "initializing_db"
    assert isinstance(payload.data, IpGeolocationAsnLookupDataModel)
    assert payload.data.total == 0
    assert payload.data.items == ()


def test_lookup_asn_unresolved_after_ready_returns_not_found() -> None:
    """Unresolved ASN lookup after readiness should map to not_found."""
    service = IpGeolocationService()
    service.publish_snapshot(_sample_read_result(), {})

    payload = service.lookup_asn_geolocation("AS99999")

    assert payload.status == "success"
    assert payload.service_state == "ready"
    assert payload.resolution_state == "not_found"
    assert isinstance(payload.data, IpGeolocationAsnLookupDataModel)
    assert payload.data.total == 0
    assert payload.data.items == ()


def test_lookup_country_found_after_publish_returns_found_with_compact_payload() -> None:
    """Matched country-code lookup should return all matched subnet records."""
    service = IpGeolocationService()
    service.publish_snapshot(
        IpGeolocationReadResult(
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
                ),
                IpGeolocationRecordModel(
                    network="1.1.1.0/24",
                    country="United States",
                    country_code="US",
                    continent="North America",
                    continent_code="NA",
                    asn="AS13335",
                    as_name="Cloudflare",
                    as_domain="cloudflare.com",
                ),
                IpGeolocationRecordModel(
                    network="9.9.9.0/24",
                    country="Germany",
                    country_code="DE",
                    continent="Europe",
                    continent_code="EU",
                    asn="AS19281",
                    as_name="Quad9",
                    as_domain="quad9.net",
                ),
            ],
            total_lines=3,
            malformed_lines=0,
        ),
        {},
    )

    payload = service.lookup_country_geolocation("us")

    assert payload.status == "success"
    assert payload.service_state == "ready"
    assert payload.resolution_state == "found"
    assert isinstance(payload.data, IpGeolocationCountryLookupDataModel)
    assert payload.data.country == "US"
    assert payload.data.total == 2
    assert len(payload.data.items) == 2
    assert payload.data.items[0].network == "8.8.8.0/24"
    assert payload.data.items[0].continent == "North America"
    assert payload.data.items[0].continent_code == "NA"
    assert payload.data.items[0].asn == "AS15169"


def test_lookup_country_unresolved_while_loading_returns_initializing_db() -> None:
    """Unresolved country-code lookup during loading should map to initializing_db."""
    service = IpGeolocationService()

    payload = service.lookup_country_geolocation("US")

    assert payload.status == "success"
    assert payload.service_state == "loading"
    assert payload.resolution_state == "initializing_db"
    assert isinstance(payload.data, IpGeolocationCountryLookupDataModel)
    assert payload.data.country == "US"
    assert payload.data.total == 0
    assert payload.data.items == ()


def test_lookup_country_unresolved_after_ready_returns_not_found() -> None:
    """Unresolved country-code lookup after readiness should map to not_found."""
    service = IpGeolocationService()
    service.publish_snapshot(_sample_read_result(), {})

    payload = service.lookup_country_geolocation("DE")

    assert payload.status == "success"
    assert payload.service_state == "ready"
    assert payload.resolution_state == "not_found"
    assert isinstance(payload.data, IpGeolocationCountryLookupDataModel)
    assert payload.data.country == "DE"
    assert payload.data.total == 0
    assert payload.data.items == ()


def test_lookup_continent_found_after_publish_returns_found_with_compact_payload() -> None:
    """Matched continent-code lookup should return all matched subnet records."""
    service = IpGeolocationService()
    service.publish_snapshot(
        IpGeolocationReadResult(
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
                ),
                IpGeolocationRecordModel(
                    network="1.1.1.0/24",
                    country="Australia",
                    country_code="AU",
                    continent="Oceania",
                    continent_code="OC",
                    asn="AS13335",
                    as_name="Cloudflare",
                    as_domain="cloudflare.com",
                ),
                IpGeolocationRecordModel(
                    network="9.9.9.0/24",
                    country="Germany",
                    country_code="DE",
                    continent="Europe",
                    continent_code="EU",
                    asn="AS19281",
                    as_name="Quad9",
                    as_domain="quad9.net",
                ),
            ],
            total_lines=3,
            malformed_lines=0,
        ),
        {},
    )

    payload = service.lookup_continent_geolocation("na")

    assert payload.status == "success"
    assert payload.service_state == "ready"
    assert payload.resolution_state == "found"
    assert isinstance(payload.data, IpGeolocationContinentLookupDataModel)
    assert payload.data.continent == "NA"
    assert payload.data.total == 1
    assert len(payload.data.items) == 1
    assert payload.data.items[0].network == "8.8.8.0/24"
    assert payload.data.items[0].country == "United States"
    assert payload.data.items[0].country_code == "US"
    assert payload.data.items[0].asn == "AS15169"


def test_lookup_continent_unresolved_while_loading_returns_initializing_db() -> None:
    """Unresolved continent-code lookup during loading should map to initializing_db."""
    service = IpGeolocationService()

    payload = service.lookup_continent_geolocation("EU")

    assert payload.status == "success"
    assert payload.service_state == "loading"
    assert payload.resolution_state == "initializing_db"
    assert isinstance(payload.data, IpGeolocationContinentLookupDataModel)
    assert payload.data.continent == "EU"
    assert payload.data.total == 0
    assert payload.data.items == ()


def test_lookup_continent_unresolved_after_ready_returns_not_found() -> None:
    """Unresolved continent-code lookup after readiness should map to not_found."""
    service = IpGeolocationService()
    service.publish_snapshot(_sample_read_result(), {})

    payload = service.lookup_continent_geolocation("EU")

    assert payload.status == "success"
    assert payload.service_state == "ready"
    assert payload.resolution_state == "not_found"
    assert isinstance(payload.data, IpGeolocationContinentLookupDataModel)
    assert payload.data.continent == "EU"
    assert payload.data.total == 0
    assert payload.data.items == ()


def test_failed_state_returns_failure_envelope() -> None:
    """Service failed state should return standard failure envelope."""
    service = IpGeolocationService()
    service._service_state = "failed"  # explicit state simulation for unit test

    payload = service.lookup_ip_geolocation("8.8.8.8")

    assert isinstance(payload, IpGeolocationLookupFailureResponseModel)
    assert payload.status == "failure"
    assert payload.service_state == "failed"
    assert payload.error.code == "IP_GEO_SERVICE_FAILED"


def test_is_snapshot_equivalent_returns_false_when_service_not_ready() -> None:
    """Equivalence check should be disabled before first successful final publish."""
    service = IpGeolocationService()
    assert service.is_snapshot_equivalent(_sample_read_result()) is False


def test_is_snapshot_equivalent_returns_true_for_same_content_different_order() -> None:
    """Equivalence should be semantic and order-insensitive."""
    service = IpGeolocationService()
    baseline = _sample_read_result()
    service.publish_snapshot(baseline, {})

    reversed_records = list(reversed(baseline.records))
    candidate = IpGeolocationReadResult(
        records=reversed_records,
        total_lines=baseline.total_lines,
        malformed_lines=baseline.malformed_lines,
    )

    assert service.is_snapshot_equivalent(candidate) is True


def test_is_snapshot_equivalent_returns_false_for_different_content() -> None:
    """Any record-field difference should break equivalence."""
    service = IpGeolocationService()
    baseline = _sample_read_result()
    service.publish_snapshot(baseline, {})

    from models.ip_geolocation import IpGeolocationRecordModel

    changed = IpGeolocationRecordModel(
        network="8.8.8.0/24",
        country="United States",
        country_code="US",
        continent="North America",
        continent_code="NA",
        asn="AS99999",
        as_name="Changed Corp",
        as_domain="changed.example",
    )
    candidate = IpGeolocationReadResult(records=[changed], total_lines=2, malformed_lines=1)

    assert service.is_snapshot_equivalent(candidate) is False


def test_apply_snapshot_delta_returns_false_when_not_ready() -> None:
    """Delta apply should be rejected before service reaches ready state."""
    service = IpGeolocationService()
    candidate = IpGeolocationReadResult(records=[_record("8.8.8.0/24", "Google LLC")], total_lines=1, malformed_lines=0)

    assert service.apply_snapshot_delta(candidate, {}) is False


def test_apply_snapshot_delta_add_remove_update_changes_snapshot() -> None:
    """Delta apply should add, remove and update rows in-place for ready snapshots."""
    service = IpGeolocationService()

    baseline = IpGeolocationReadResult(
        records=[
            _record("8.8.8.0/24", "Google LLC"),
            _record("9.9.9.0/24", "Quad9"),
        ],
        total_lines=2,
        malformed_lines=0,
    )
    service.publish_snapshot(baseline, {})

    candidate = IpGeolocationReadResult(
        records=[
            _record("8.8.8.0/24", "Google Updated"),
            _record("1.1.1.0/24", "Cloudflare"),
        ],
        total_lines=2,
        malformed_lines=0,
    )

    applied = service.apply_snapshot_delta(candidate, {})
    assert applied is True

    found_google = service.lookup_ip_geolocation("8.8.8.8")
    assert isinstance(found_google, IpGeolocationLookupSuccessResponseModel)
    assert found_google.resolution_state == "found"
    assert isinstance(found_google.data, IpGeolocationLookupDataModel)
    assert found_google.data.as_name == "Google Updated"

    found_added = service.lookup_ip_geolocation("1.1.1.1")
    assert isinstance(found_added, IpGeolocationLookupSuccessResponseModel)
    assert found_added.resolution_state == "found"
    assert isinstance(found_added.data, IpGeolocationLookupDataModel)
    assert found_added.data.as_name == "Cloudflare"

    removed = service.lookup_ip_geolocation("9.9.9.9")
    assert isinstance(removed, IpGeolocationLookupSuccessResponseModel)
    assert removed.resolution_state == "not_found"


def test_apply_snapshot_delta_noop_keeps_snapshot_and_returns_true() -> None:
    """Equivalent candidate should return True without changing semantics."""
    service = IpGeolocationService()
    baseline = IpGeolocationReadResult(records=[_record("8.8.8.0/24", "Google LLC")], total_lines=1, malformed_lines=0)
    service.publish_snapshot(baseline, {})

    candidate = IpGeolocationReadResult(records=[_record("8.8.8.0/24", "Google LLC")], total_lines=1, malformed_lines=0)
    assert service.apply_snapshot_delta(candidate, {}) is True

    payload = service.lookup_ip_geolocation("8.8.8.8")
    assert isinstance(payload, IpGeolocationLookupSuccessResponseModel)
    assert payload.resolution_state == "found"
    assert isinstance(payload.data, IpGeolocationLookupDataModel)
    assert payload.data.as_name == "Google LLC"
