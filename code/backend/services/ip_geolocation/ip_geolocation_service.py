"""Read-facing IP geolocation service facade.

This service owns runtime read state, active lookup snapshot, and the publish
entrypoint used by the domain refresher.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import ipaddress
from threading import RLock
from typing import Any, cast

from infra.ip_geolocation import IpGeolocationReadResult
from models.ip_geolocation import (
    IpGeolocationErrorModel,
    IpGeolocationLoadCountersModel,
    IpGeolocationLoadStatusModel,
    IpGeolocationLookupDataModel,
    IpGeolocationLookupFailureResponseModel,
    IpGeolocationLookupResponseModel,
    IpGeolocationLookupSuccessResponseModel,
    IpGeolocationRecordModel,
    IpGeolocationRefreshMetadataModel,
    IpGeolocationSourceFingerprintModel,
    ServiceState,
)


@dataclass(frozen=True)
class _SnapshotEntry:
    network: ipaddress._BaseNetwork
    record: IpGeolocationRecordModel


class IpGeolocationService:
    """Own active snapshot and expose lookup/status read contracts."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._service_state: ServiceState = "loading"
        self._snapshot: tuple[_SnapshotEntry, ...] = ()
        self._staging_snapshot: list[_SnapshotEntry] = []
        self._counters = IpGeolocationLoadCountersModel(total=0, loaded=0, malformed=0)
        self._last_loaded_at: datetime | None = None
        self._refresh = IpGeolocationRefreshMetadataModel()

    def initialize_ip_geolocation_dataset(self) -> None:
        """Set deterministic startup state before first refresher publish."""
        with self._lock:
            self._service_state = "loading"
            self._snapshot = ()
            self._staging_snapshot = []
            self._counters = IpGeolocationLoadCountersModel(total=0, loaded=0, malformed=0)
            self._last_loaded_at = None
            self._refresh = IpGeolocationRefreshMetadataModel()

    def publish_snapshot(self, new_snapshot: IpGeolocationReadResult, metadata: dict[str, Any]) -> None:
        """Build and atomically swap active snapshot on successful parse output."""
        built_entries: list[_SnapshotEntry] = []
        for record in new_snapshot.records:
            network = ipaddress.ip_network(record.network, strict=False)
            built_entries.append(_SnapshotEntry(network=network, record=record))

        fingerprint = self._extract_fingerprint_model(metadata.get("source_fingerprint"))
        next_refresh = IpGeolocationRefreshMetadataModel(
            last_refresh_error=None,
            last_refresh_attempt_at=self._resolve_datetime(metadata.get("last_refresh_attempt_at"))
            or self._refresh.last_refresh_attempt_at,
            last_refresh_succeeded_at=self._resolve_datetime(metadata.get("last_refresh_succeeded_at"))
            or datetime.now(UTC),
            active_source_fingerprint=fingerprint,
            refresh_attempt_count=self._resolve_int(metadata.get("refresh_attempt_count"), self._refresh.refresh_attempt_count),
            refresh_success_count=self._resolve_int(metadata.get("refresh_success_count"), self._refresh.refresh_success_count),
            refresh_failure_count=self._resolve_int(metadata.get("refresh_failure_count"), self._refresh.refresh_failure_count),
        )

        next_total = self._resolve_int(metadata.get("total_lines"), new_snapshot.total_lines)
        next_malformed = self._resolve_int(metadata.get("malformed_lines"), new_snapshot.malformed_lines)
        is_final_chunk = self._resolve_bool(metadata.get("is_final_chunk"), True)

        with self._lock:
            if is_final_chunk:
                self._staging_snapshot.extend(built_entries)
                self._snapshot = tuple(self._staging_snapshot)
                self._staging_snapshot = []
            else:
                self._staging_snapshot.extend(built_entries)
                self._snapshot = tuple(self._staging_snapshot)
            self._counters = IpGeolocationLoadCountersModel(
                total=next_total,
                loaded=len(self._snapshot) if is_final_chunk else len(self._staging_snapshot),
                malformed=next_malformed,
            )
            self._last_loaded_at = datetime.now(UTC)
            self._refresh = next_refresh
            self._service_state = "ready" if is_final_chunk else "loading"

    def lookup_ip_geolocation(self, ip: str) -> IpGeolocationLookupResponseModel:
        """Resolve a requested IP against the active in-memory snapshot."""
        with self._lock:
            service_state = self._service_state
            snapshot = self._snapshot

        if service_state == "failed":
            return IpGeolocationLookupFailureResponseModel(
                status="failure",
                service_state="failed",
                error=IpGeolocationErrorModel(
                    code="IP_GEO_SERVICE_FAILED",
                    message="IP geolocation service is in failed state",
                ),
            )

        try:
            requested_ip = ipaddress.ip_address(ip.strip())
        except ValueError:
            return IpGeolocationLookupSuccessResponseModel(
                status="success",
                service_state=service_state,
                resolution_state="not_found" if service_state == "ready" else "initializing_db",
                data=IpGeolocationLookupDataModel(
                    ip=ip,
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

        for entry in snapshot:
            if requested_ip in entry.network:
                record = entry.record
                return IpGeolocationLookupSuccessResponseModel(
                    status="success",
                    service_state=service_state,
                    resolution_state="found",
                    data=IpGeolocationLookupDataModel(
                        ip=str(requested_ip),
                        network=record.network,
                        country=record.country,
                        country_code=record.country_code,
                        continent=record.continent,
                        continent_code=record.continent_code,
                        asn=record.asn,
                        as_name=record.as_name,
                        as_domain=record.as_domain,
                    ),
                )

        return IpGeolocationLookupSuccessResponseModel(
            status="success",
            service_state=service_state,
            resolution_state="not_found" if service_state == "ready" else "initializing_db",
            data=IpGeolocationLookupDataModel(
                ip=str(requested_ip),
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

    def get_ip_geolocation_load_status(self) -> IpGeolocationLoadStatusModel:
        """Return current read-facing load status snapshot."""
        with self._lock:
            return IpGeolocationLoadStatusModel(
                service_state=self._service_state,
                counters=self._counters,
                last_loaded_at=self._last_loaded_at,
                refresh=self._refresh,
            )

    @staticmethod
    def _resolve_int(value: object, default: int) -> int:
        if value is None:
            return default
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            return int(value)
        return default

    @staticmethod
    def _resolve_datetime(value: object) -> datetime | None:
        return value if isinstance(value, datetime) else None

    @staticmethod
    def _resolve_bool(value: object, default: bool) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value != 0
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        return default

    @staticmethod
    def _extract_fingerprint_model(value: object) -> IpGeolocationSourceFingerprintModel | None:
        if value is None:
            return None

        inode = getattr(value, "inode", None)
        mtime_ns = getattr(value, "mtime_ns", None)
        if inode is None or mtime_ns is None:
            return None

        inode_value = IpGeolocationService._resolve_int(cast(object, inode), -1)
        mtime_value = IpGeolocationService._resolve_int(cast(object, mtime_ns), -1)
        if inode_value < 0 or mtime_value < 0:
            return None

        return IpGeolocationSourceFingerprintModel(inode=inode_value, mtime_ns=mtime_value)


__all__ = ["IpGeolocationService"]
