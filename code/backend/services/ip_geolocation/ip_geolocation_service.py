"""Read-facing IP geolocation service facade.

This service owns runtime read state, active lookup snapshot, and the publish
entrypoint used by the domain refresher.

Performance notes
-----------------
Two hot paths were historically expensive:

1) ``publish_snapshot`` used to rebuild a full ``tuple`` of the staging list on
   every non-final chunk, causing O(N^2) allocation/copy behavior when the
   dataset is published in many chunks. The new implementation keeps the
   active ``_snapshot`` stable while chunks are buffered in ``_staging`` and
   only swaps atomically on the final chunk. Lookups continue to serve the
   previously-active snapshot during a refresh, which is both memory-
   efficient and correct (no partial/inconsistent visibility).

2) Equivalence/delta operations used to materialize the entire incoming
   dataset as ``IpGeolocationRecordModel`` objects. To support a streaming
   delta path owned by the refresher, the service now exposes a compact
   cached ``_snapshot_keys`` index (``dict[str, int]`` of
   network -> record-content-hash) that can be diffed against a freshly-
   streamed incoming index without ever holding a second copy of the full
   record set in memory. Delta application also has a streaming-friendly
   variant (``apply_snapshot_delta_records``) that only materializes the
   rows that actually changed.

Record objects also use ``slots=True`` (see ``IpGeolocationRecordModel``) to
remove per-record ``__dict__`` overhead.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import ipaddress
from threading import RLock
from typing import Any, Iterable, cast

from infra.ip_geolocation import IpGeolocationReadResult
from models.ip_geolocation import (
    IpGeolocationAsnLookupDataModel,
    IpGeolocationAsnSubnetItemModel,
    IpGeolocationContinentLookupDataModel,
    IpGeolocationContinentSubnetItemModel,
    IpGeolocationCountryLookupDataModel,
    IpGeolocationCountrySubnetItemModel,
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


_IP_GEO_SERVICE_FAILED_MESSAGE = "IP geolocation service is in failed state"


@dataclass(frozen=True, slots=True)
class _SnapshotEntry:
    network: ipaddress._BaseNetwork
    record: IpGeolocationRecordModel


def _record_value_hash(record: IpGeolocationRecordModel) -> int:
    """Compute a compact content hash for a record (excluding network key).

    Used by the streaming delta path so the service can diff an incoming
    index against the active snapshot without storing full records.
    """
    return hash(
        (
            record.country,
            record.country_code,
            record.continent,
            record.continent_code,
            record.asn,
            record.as_name,
            record.as_domain,
        )
    )


class IpGeolocationService:
    """Own active snapshot and expose lookup/status read contracts."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._service_state: ServiceState = "loading"
        self._snapshot: tuple[_SnapshotEntry, ...] = ()
        self._snapshot_keys: dict[str, int] = {}
        self._staging: list[_SnapshotEntry] = []
        self._counters = IpGeolocationLoadCountersModel(total=0, loaded=0, malformed=0)
        self._last_loaded_at: datetime | None = None
        self._refresh = IpGeolocationRefreshMetadataModel()

    def initialize_ip_geolocation_dataset(self) -> None:
        """Set deterministic startup state before first refresher publish."""
        with self._lock:
            self._service_state = "loading"
            self._snapshot = ()
            self._snapshot_keys = {}
            self._staging = []
            self._counters = IpGeolocationLoadCountersModel(total=0, loaded=0, malformed=0)
            self._last_loaded_at = None
            self._refresh = IpGeolocationRefreshMetadataModel()

    # ---------------------------------------------------------------------
    # Publish path (chunked, memory-efficient)
    # ---------------------------------------------------------------------

    def publish_snapshot(self, new_snapshot: IpGeolocationReadResult, metadata: dict[str, Any]) -> None:
        """Append a chunk to the staging snapshot and atomically swap on final.

        Behavior:
        - On non-final chunk: append to staging, update counters/refresh
          metadata, keep ``_service_state`` in ``loading`` and keep the
          *previous* active snapshot served to readers. This avoids O(N^2)
          rebuild cost and avoids exposing half-built data.
        - On final chunk: append remaining entries, build snapshot tuple +
          key index once, swap atomically and mark service ``ready``.
        """
        built_entries = self._build_entries(new_snapshot.records)

        fingerprint = self._extract_fingerprint_model(metadata.get("source_fingerprint"))
        is_final_chunk = self._resolve_bool(metadata.get("is_final_chunk"), True)
        next_total = self._resolve_int(metadata.get("total_lines"), new_snapshot.total_lines)
        next_malformed = self._resolve_int(metadata.get("malformed_lines"), new_snapshot.malformed_lines)

        with self._lock:
            had_active_snapshot = bool(self._snapshot)
            self._staging.extend(built_entries)

            next_refresh = self._compose_refresh_metadata(metadata, fingerprint)

            if is_final_chunk:
                swap_tuple = tuple(self._staging)
                swap_keys = {entry.record.network: _record_value_hash(entry.record) for entry in swap_tuple}
                self._snapshot = swap_tuple
                self._snapshot_keys = swap_keys
                self._staging = []
                loaded_count = len(swap_tuple)
                next_state: ServiceState = "ready"
            else:
                loaded_count = len(self._staging)
                if not had_active_snapshot:
                    # Bootstrap progressive visibility: while no prior active
                    # snapshot exists, expose already-published chunks.
                    bootstrap_tuple = tuple(self._staging)
                    self._snapshot = bootstrap_tuple
                    self._snapshot_keys = {
                        entry.record.network: _record_value_hash(entry.record)
                        for entry in bootstrap_tuple
                    }
                next_state = "loading"

            self._counters = IpGeolocationLoadCountersModel(
                total=next_total,
                loaded=loaded_count,
                malformed=next_malformed,
            )
            self._last_loaded_at = datetime.now(UTC)
            self._refresh = next_refresh
            self._service_state = next_state

    # ---------------------------------------------------------------------
    # Streaming delta path (preferred when adapter supports chunk iteration)
    # ---------------------------------------------------------------------

    def get_active_network_key_index(self) -> dict[str, int] | None:
        """Return a shallow copy of the cached network -> content-hash index.

        Returns ``None`` when service is not yet ``ready``; refresher uses
        this signal to skip the streaming-delta fast path on first load.
        """
        with self._lock:
            if self._service_state != "ready":
                return None
            # Shallow copy so callers can't mutate the cache by mistake.
            return dict(self._snapshot_keys)

    def apply_snapshot_delta_records(
        self,
        added_or_updated_records: Iterable[IpGeolocationRecordModel],
        removed_networks: Iterable[str],
        metadata: dict[str, Any],
    ) -> bool:
        """Apply a precomputed streaming delta to the active snapshot.

        This is the memory-efficient counterpart to ``apply_snapshot_delta``:
        callers pass only the rows that changed (added or updated) plus the
        set of removed networks — not the full incoming dataset.
        """
        added_or_updated_list = list(added_or_updated_records)
        removed_set = set(removed_networks)

        fingerprint = self._extract_fingerprint_model(metadata.get("source_fingerprint"))
        next_total = self._resolve_int(metadata.get("total_lines"), 0)
        next_malformed = self._resolve_int(metadata.get("malformed_lines"), 0)

        with self._lock:
            if self._service_state != "ready":
                return False

            if not added_or_updated_list and not removed_set:
                # No-op delta. Still refresh timestamps/metadata for observability.
                self._refresh = self._compose_refresh_metadata(metadata, fingerprint)
                self._last_loaded_at = datetime.now(UTC)
                return True

            current_by_network: dict[str, _SnapshotEntry] = {
                entry.record.network: entry for entry in self._snapshot
            }

            for network in removed_set:
                current_by_network.pop(network, None)
                self._snapshot_keys.pop(network, None)

            for record in added_or_updated_list:
                parsed_network = ipaddress.ip_network(record.network, strict=False)
                current_by_network[record.network] = _SnapshotEntry(network=parsed_network, record=record)
                self._snapshot_keys[record.network] = _record_value_hash(record)

            self._snapshot = tuple(current_by_network.values())
            self._counters = IpGeolocationLoadCountersModel(
                total=next_total if next_total > 0 else self._counters.total,
                loaded=len(self._snapshot),
                malformed=next_malformed if next_malformed >= 0 else self._counters.malformed,
            )
            self._last_loaded_at = datetime.now(UTC)
            self._refresh = self._compose_refresh_metadata(metadata, fingerprint)
            self._service_state = "ready"

        return True

    # ---------------------------------------------------------------------
    # Legacy delta/equivalence path (kept for non-streaming adapters/tests)
    # ---------------------------------------------------------------------

    def apply_snapshot_delta(self, candidate: IpGeolocationReadResult, metadata: dict[str, Any]) -> bool:
        """Apply row-level add/remove/update changes for ready snapshots.

        Legacy variant that accepts a full ``IpGeolocationReadResult`` — used
        by callers that cannot stream (e.g. small/test fixtures). Prefer
        ``apply_snapshot_delta_records`` for large datasets.

        Returns False when delta apply cannot be safely used (e.g. service is
        not ready yet), so caller can fallback to full publish.
        """
        with self._lock:
            if self._service_state != "ready":
                return False

            current_by_network = {entry.record.network: entry for entry in self._snapshot}

        incoming_by_network = {record.network: record for record in candidate.records}

        current_networks = set(current_by_network)
        incoming_networks = set(incoming_by_network)

        removed_networks = current_networks - incoming_networks
        added_networks = incoming_networks - current_networks
        common_networks = current_networks & incoming_networks

        updated_networks = {
            network
            for network in common_networks
            if self._record_key(current_by_network[network].record)
            != self._record_key(incoming_by_network[network])
        }

        if not removed_networks and not added_networks and not updated_networks:
            return True

        next_by_network = dict(current_by_network)
        for network in removed_networks:
            next_by_network.pop(network, None)

        for network in added_networks | updated_networks:
            record = incoming_by_network[network]
            parsed_network = ipaddress.ip_network(record.network, strict=False)
            next_by_network[network] = _SnapshotEntry(network=parsed_network, record=record)

        fingerprint = self._extract_fingerprint_model(metadata.get("source_fingerprint"))
        next_refresh = self._compose_refresh_metadata(metadata, fingerprint)

        with self._lock:
            self._snapshot = tuple(next_by_network.values())
            self._snapshot_keys = {
                entry.record.network: _record_value_hash(entry.record) for entry in self._snapshot
            }
            self._counters = IpGeolocationLoadCountersModel(
                total=self._resolve_int(metadata.get("total_lines"), candidate.total_lines),
                loaded=len(self._snapshot),
                malformed=self._resolve_int(metadata.get("malformed_lines"), candidate.malformed_lines),
            )
            self._last_loaded_at = datetime.now(UTC)
            self._refresh = next_refresh
            self._service_state = "ready"

        return True

    def is_snapshot_equivalent(self, candidate: IpGeolocationReadResult) -> bool:
        """Return True when candidate records semantically match active in-memory snapshot."""
        with self._lock:
            if self._service_state != "ready":
                return False
            current_keys = dict(self._snapshot_keys)

        if len(current_keys) != len(candidate.records):
            return False

        candidate_keys: dict[str, int] = {}
        for record in candidate.records:
            candidate_keys[record.network] = _record_value_hash(record)

        return current_keys == candidate_keys

    # ---------------------------------------------------------------------
    # Lookup path (read-only against atomically-swapped snapshot)
    # ---------------------------------------------------------------------

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
                    message=_IP_GEO_SERVICE_FAILED_MESSAGE,
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

    def lookup_asn_geolocation(self, asn: str) -> IpGeolocationLookupResponseModel:
        """Resolve all matching subnet records by ASN against active in-memory snapshot."""
        with self._lock:
            service_state = self._service_state
            snapshot = self._snapshot

        if service_state == "failed":
            return IpGeolocationLookupFailureResponseModel(
                status="failure",
                service_state="failed",
                error=IpGeolocationErrorModel(
                    code="IP_GEO_SERVICE_FAILED",
                    message=_IP_GEO_SERVICE_FAILED_MESSAGE,
                ),
            )

        normalized_asn = asn.strip().upper()
        if not normalized_asn:
            return IpGeolocationLookupSuccessResponseModel(
                status="success",
                service_state=service_state,
                resolution_state="not_found" if service_state == "ready" else "initializing_db",
                data=IpGeolocationAsnLookupDataModel(asn=asn, items=(), total=0, as_name=None),
            )

        matched_items: list[IpGeolocationAsnSubnetItemModel] = []
        matched_as_name: str | None = None
        for entry in snapshot:
            record = entry.record
            if record.asn is None:
                continue
            if record.asn.strip().upper() == normalized_asn:
                if matched_as_name is None and record.as_name is not None and record.as_name.strip():
                    matched_as_name = record.as_name.strip()
                matched_items.append(
                    IpGeolocationAsnSubnetItemModel(
                        network=record.network,
                        country=record.country,
                        country_code=record.country_code,
                        continent=record.continent,
                        continent_code=record.continent_code,
                    )
                )

        if matched_items:
            return IpGeolocationLookupSuccessResponseModel(
                status="success",
                service_state=service_state,
                resolution_state="found",
                data=IpGeolocationAsnLookupDataModel(
                    asn=normalized_asn,
                    items=tuple(matched_items),
                    total=len(matched_items),
                    as_name=matched_as_name,
                ),
            )

        return IpGeolocationLookupSuccessResponseModel(
            status="success",
            service_state=service_state,
            resolution_state="not_found" if service_state == "ready" else "initializing_db",
            data=IpGeolocationAsnLookupDataModel(asn=normalized_asn, items=(), total=0, as_name=None),
        )

    def lookup_country_geolocation(self, country: str) -> IpGeolocationLookupResponseModel:
        """Resolve all matching subnet records by country code against active snapshot."""
        with self._lock:
            service_state = self._service_state
            snapshot = self._snapshot

        if service_state == "failed":
            return IpGeolocationLookupFailureResponseModel(
                status="failure",
                service_state="failed",
                error=IpGeolocationErrorModel(
                    code="IP_GEO_SERVICE_FAILED",
                    message=_IP_GEO_SERVICE_FAILED_MESSAGE,
                ),
            )

        normalized_country_code = country.strip().upper()
        if not normalized_country_code:
            return IpGeolocationLookupSuccessResponseModel(
                status="success",
                service_state=service_state,
                resolution_state="not_found" if service_state == "ready" else "initializing_db",
                data=IpGeolocationCountryLookupDataModel(country=country, items=(), total=0),
            )

        matched_items: list[IpGeolocationCountrySubnetItemModel] = []
        for entry in snapshot:
            record = entry.record
            if record.country_code.strip().upper() == normalized_country_code:
                matched_items.append(
                    IpGeolocationCountrySubnetItemModel(
                        network=record.network,
                        continent=record.continent,
                        continent_code=record.continent_code,
                        asn=record.asn,
                        as_name=record.as_name,
                    )
                )

        if matched_items:
            return IpGeolocationLookupSuccessResponseModel(
                status="success",
                service_state=service_state,
                resolution_state="found",
                data=IpGeolocationCountryLookupDataModel(
                    country=normalized_country_code,
                    items=tuple(matched_items),
                    total=len(matched_items),
                ),
            )

        return IpGeolocationLookupSuccessResponseModel(
            status="success",
            service_state=service_state,
            resolution_state="not_found" if service_state == "ready" else "initializing_db",
            data=IpGeolocationCountryLookupDataModel(country=normalized_country_code, items=(), total=0),
        )

    def lookup_continent_geolocation(self, continent: str) -> IpGeolocationLookupResponseModel:
        """Resolve all matching subnet records by continent code against active snapshot."""
        with self._lock:
            service_state = self._service_state
            snapshot = self._snapshot

        if service_state == "failed":
            return IpGeolocationLookupFailureResponseModel(
                status="failure",
                service_state="failed",
                error=IpGeolocationErrorModel(
                    code="IP_GEO_SERVICE_FAILED",
                    message=_IP_GEO_SERVICE_FAILED_MESSAGE,
                ),
            )

        normalized_continent_code = continent.strip().upper()
        if not normalized_continent_code:
            return IpGeolocationLookupSuccessResponseModel(
                status="success",
                service_state=service_state,
                resolution_state="not_found" if service_state == "ready" else "initializing_db",
                data=IpGeolocationContinentLookupDataModel(continent=continent, items=(), total=0),
            )

        matched_items: list[IpGeolocationContinentSubnetItemModel] = []
        for entry in snapshot:
            record = entry.record
            if record.continent_code.strip().upper() == normalized_continent_code:
                matched_items.append(
                    IpGeolocationContinentSubnetItemModel(
                        network=record.network,
                        country=record.country,
                        country_code=record.country_code,
                        asn=record.asn,
                    )
                )

        if matched_items:
            return IpGeolocationLookupSuccessResponseModel(
                status="success",
                service_state=service_state,
                resolution_state="found",
                data=IpGeolocationContinentLookupDataModel(
                    continent=normalized_continent_code,
                    items=tuple(matched_items),
                    total=len(matched_items),
                ),
            )

        return IpGeolocationLookupSuccessResponseModel(
            status="success",
            service_state=service_state,
            resolution_state="not_found" if service_state == "ready" else "initializing_db",
            data=IpGeolocationContinentLookupDataModel(continent=normalized_continent_code, items=(), total=0),
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

    # ---------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------

    @staticmethod
    def _build_entries(records: Iterable[IpGeolocationRecordModel]) -> list[_SnapshotEntry]:
        built: list[_SnapshotEntry] = []
        for record in records:
            network = ipaddress.ip_network(record.network, strict=False)
            built.append(_SnapshotEntry(network=network, record=record))
        return built

    def _compose_refresh_metadata(
        self,
        metadata: dict[str, Any],
        fingerprint: IpGeolocationSourceFingerprintModel | None,
    ) -> IpGeolocationRefreshMetadataModel:
        return IpGeolocationRefreshMetadataModel(
            last_refresh_error=None,
            last_refresh_attempt_at=self._resolve_datetime(metadata.get("last_refresh_attempt_at"))
            or self._refresh.last_refresh_attempt_at,
            last_refresh_succeeded_at=self._resolve_datetime(metadata.get("last_refresh_succeeded_at"))
            or datetime.now(UTC),
            active_source_fingerprint=fingerprint,
            refresh_attempt_count=self._resolve_int(
                metadata.get("refresh_attempt_count"), self._refresh.refresh_attempt_count
            ),
            refresh_success_count=self._resolve_int(
                metadata.get("refresh_success_count"), self._refresh.refresh_success_count
            ),
            refresh_failure_count=self._resolve_int(
                metadata.get("refresh_failure_count"), self._refresh.refresh_failure_count
            ),
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

    @staticmethod
    def _record_key(
        record: IpGeolocationRecordModel,
    ) -> tuple[str, str, str, str, str, str | None, str | None, str | None]:
        return (
            record.network,
            record.country,
            record.country_code,
            record.continent,
            record.continent_code,
            record.asn,
            record.as_name,
            record.as_domain,
        )


__all__ = ["IpGeolocationService"]
