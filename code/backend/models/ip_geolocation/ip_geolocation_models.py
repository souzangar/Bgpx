"""Shared models for IP geolocation feature contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


ServiceState = Literal["loading", "ready", "failed"]
EnvelopeStatus = Literal["success", "failure"]
ResolutionState = Literal["found", "initializing_db", "not_found"]


@dataclass(frozen=True)
class IpGeolocationRecordModel:
    """Normalized IP geolocation record loaded from provider source."""

    network: str
    country: str
    country_code: str
    continent: str
    continent_code: str
    asn: str | None
    as_name: str | None
    as_domain: str | None

    def __post_init__(self) -> None:
        """Validate mandatory textual fields for normalized records."""
        if not self.network.strip():
            raise ValueError("network must be a non-empty string")

        if not self.country.strip():
            raise ValueError("country must be a non-empty string")

        if not self.country_code.strip():
            raise ValueError("country_code must be a non-empty string")

        if not self.continent.strip():
            raise ValueError("continent must be a non-empty string")

        if not self.continent_code.strip():
            raise ValueError("continent_code must be a non-empty string")


@dataclass(frozen=True)
class IpGeolocationLookupDataModel:
    """Lookup payload containing requested IP and resolved geolocation fields."""

    ip: str
    network: str | None
    country: str | None
    country_code: str | None
    continent: str | None
    continent_code: str | None
    asn: str | None
    as_name: str | None
    as_domain: str | None

    def __post_init__(self) -> None:
        """Validate lookup payload constraints."""
        if not self.ip.strip():
            raise ValueError("ip must be a non-empty string")


@dataclass(frozen=True)
class IpGeolocationLoadCountersModel:
    """Dataset loading and parsing counters."""

    total: int
    loaded: int
    malformed: int

    def __post_init__(self) -> None:
        """Validate non-negative counter constraints."""
        if self.total < 0:
            raise ValueError("total cannot be negative")

        if self.loaded < 0:
            raise ValueError("loaded cannot be negative")

        if self.malformed < 0:
            raise ValueError("malformed cannot be negative")


@dataclass(frozen=True)
class IpGeolocationSourceFingerprintModel:
    """Active source fingerprint used for refresh change detection observability."""

    inode: int
    mtime_ns: int

    def __post_init__(self) -> None:
        """Validate non-negative fingerprint fields."""
        if self.inode < 0:
            raise ValueError("inode cannot be negative")

        if self.mtime_ns < 0:
            raise ValueError("mtime_ns cannot be negative")


@dataclass(frozen=True)
class IpGeolocationRefreshMetadataModel:
    """Optional refresh observability metadata exposed in status responses."""

    last_refresh_error: str | None = None
    last_refresh_attempt_at: datetime | None = None
    last_refresh_succeeded_at: datetime | None = None
    active_source_fingerprint: IpGeolocationSourceFingerprintModel | None = None
    refresh_attempt_count: int = 0
    refresh_success_count: int = 0
    refresh_failure_count: int = 0

    def __post_init__(self) -> None:
        """Validate refresh counters remain non-negative."""
        if self.refresh_attempt_count < 0:
            raise ValueError("refresh_attempt_count cannot be negative")

        if self.refresh_success_count < 0:
            raise ValueError("refresh_success_count cannot be negative")

        if self.refresh_failure_count < 0:
            raise ValueError("refresh_failure_count cannot be negative")


@dataclass(frozen=True)
class IpGeolocationLoadStatusModel:
    """Runtime load/status snapshot for the geolocation service."""

    service_state: ServiceState
    counters: IpGeolocationLoadCountersModel
    last_loaded_at: datetime | None = None
    refresh: IpGeolocationRefreshMetadataModel | None = None


@dataclass(frozen=True)
class IpGeolocationErrorModel:
    """Standardized error payload for failure envelopes."""

    code: str
    message: str

    def __post_init__(self) -> None:
        """Validate error payload fields."""
        if not self.code.strip():
            raise ValueError("code must be a non-empty string")

        if not self.message.strip():
            raise ValueError("message must be a non-empty string")


@dataclass(frozen=True)
class IpGeolocationLookupSuccessResponseModel:
    """Lookup success envelope containing business-level resolution state."""

    status: Literal["success"]
    service_state: ServiceState
    resolution_state: ResolutionState
    data: IpGeolocationLookupDataModel


@dataclass(frozen=True)
class IpGeolocationLookupFailureResponseModel:
    """Lookup failure envelope for service-level failures."""

    status: Literal["failure"]
    service_state: Literal["failed"]
    error: IpGeolocationErrorModel


IpGeolocationLookupResponseModel = (
    IpGeolocationLookupSuccessResponseModel | IpGeolocationLookupFailureResponseModel
)


__all__ = [
    "EnvelopeStatus",
    "IpGeolocationErrorModel",
    "IpGeolocationLoadCountersModel",
    "IpGeolocationLoadStatusModel",
    "IpGeolocationLookupDataModel",
    "IpGeolocationLookupFailureResponseModel",
    "IpGeolocationLookupResponseModel",
    "IpGeolocationLookupSuccessResponseModel",
    "IpGeolocationRecordModel",
    "IpGeolocationRefreshMetadataModel",
    "IpGeolocationSourceFingerprintModel",
    "ResolutionState",
    "ServiceState",
]
