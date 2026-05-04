"""Unit tests for IP geolocation shared models."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest


BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from models.ip_geolocation import (  # noqa: E402
    IpGeolocationErrorModel,
    IpGeolocationLoadCountersModel,
    IpGeolocationLookupDataModel,
    IpGeolocationLookupFailureResponseModel,
    IpGeolocationLookupSuccessResponseModel,
    IpGeolocationRecordModel,
    IpGeolocationRefreshMetadataModel,
    IpGeolocationSourceFingerprintModel,
)


def test_ip_geolocation_record_model_requires_non_empty_required_fields() -> None:
    """Required non-null textual fields should reject empty values."""
    with pytest.raises(ValueError, match="network must be a non-empty string"):
        IpGeolocationRecordModel(
            network=" ",
            country="Australia",
            country_code="AU",
            continent="Oceania",
            continent_code="OC",
            asn=None,
            as_name=None,
            as_domain=None,
        )


def test_ip_geolocation_load_counters_reject_negative_values() -> None:
    """Load counters must remain non-negative."""
    with pytest.raises(ValueError, match="malformed cannot be negative"):
        IpGeolocationLoadCountersModel(total=10, loaded=8, malformed=-1)


def test_lookup_data_requires_non_empty_ip() -> None:
    """Lookup payload requires non-empty requested IP field."""
    with pytest.raises(ValueError, match="ip must be a non-empty string"):
        IpGeolocationLookupDataModel(
            ip="",
            network=None,
            country=None,
            country_code=None,
            continent=None,
            continent_code=None,
            asn=None,
            as_name=None,
            as_domain=None,
        )


def test_lookup_success_response_supports_two_axis_contract_values() -> None:
    """Success model should carry service state + resolution state + data."""
    payload = IpGeolocationLookupSuccessResponseModel(
        status="success",
        service_state="loading",
        resolution_state="initializing_db",
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

    assert payload.status == "success"
    assert payload.service_state == "loading"
    assert payload.resolution_state == "initializing_db"


def test_lookup_failure_response_requires_structured_error() -> None:
    """Failure envelope should include failed service state and error payload."""
    payload = IpGeolocationLookupFailureResponseModel(
        status="failure",
        service_state="failed",
        error=IpGeolocationErrorModel(
            code="IP_GEO_INIT_FAILED",
            message="Failed to load geolocation dataset",
        ),
    )

    assert payload.status == "failure"
    assert payload.service_state == "failed"
    assert payload.error.code == "IP_GEO_INIT_FAILED"


def test_source_fingerprint_model_rejects_negative_values() -> None:
    """Source fingerprint fields should remain non-negative."""
    with pytest.raises(ValueError, match="inode cannot be negative"):
        IpGeolocationSourceFingerprintModel(inode=-1, mtime_ns=100)

    with pytest.raises(ValueError, match="mtime_ns cannot be negative"):
        IpGeolocationSourceFingerprintModel(inode=1, mtime_ns=-100)


def test_refresh_metadata_model_exposes_stage4_fields() -> None:
    """Refresh metadata should support counters and active source fingerprint."""
    metadata = IpGeolocationRefreshMetadataModel(
        active_source_fingerprint=IpGeolocationSourceFingerprintModel(inode=42, mtime_ns=123456789),
        refresh_attempt_count=10,
        refresh_success_count=7,
        refresh_failure_count=3,
    )

    assert metadata.active_source_fingerprint is not None
    assert metadata.active_source_fingerprint.inode == 42
    assert metadata.refresh_attempt_count == 10
    assert metadata.refresh_success_count == 7
    assert metadata.refresh_failure_count == 3


def test_refresh_metadata_model_rejects_negative_counters() -> None:
    """Refresh metadata counters should remain non-negative."""
    with pytest.raises(ValueError, match="refresh_attempt_count cannot be negative"):
        IpGeolocationRefreshMetadataModel(refresh_attempt_count=-1)

    with pytest.raises(ValueError, match="refresh_success_count cannot be negative"):
        IpGeolocationRefreshMetadataModel(refresh_success_count=-1)

    with pytest.raises(ValueError, match="refresh_failure_count cannot be negative"):
        IpGeolocationRefreshMetadataModel(refresh_failure_count=-1)
