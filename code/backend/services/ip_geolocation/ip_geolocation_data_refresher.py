"""IP geolocation refresher with event-based, JSON-configured logging.

Logging model (human + AI agent guidance)
-----------------------------------------
- This module emits logs through `event_logger` (see `get_component_event_logger`).
- Runtime logging behavior is configured in:
  `code/backend/data/configs/logging_config.json`
- Component key for this file: `ip_geo_refresher`

Important rules when editing/adding logs
---------------------------------------
1) Every `event_logger.log("<event_id>", ...)` / `event_logger.exception("<event_id>", ...)`
   should have a matching event entry in `logging_config.json` under:
   `components.ip_geo_refresher.events`.
2) If you add a new event ID in code, update JSON in the same change.
3) Keep event IDs stable and descriptive (for example: `poll_started`, `refresh_failed`).

Hot-reload behavior
-------------------
- Event-level config is reloaded in-process when `logging_config.json` changes.
- No backend process restart is required.
- New JSON values apply to the next logging cycle/event emission.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import os
import time
from collections.abc import Iterator
from typing import Any, Callable, Protocol, cast

from infra.ip_geolocation import (
    DATASET_PATH,
    IpGeolocationIpinfoJsonFileReaderAdapter,
    IpGeolocationReadResult,
)
from services.logging.logging_service import get_component_event_logger

event_logger = get_component_event_logger("ip_geo_refresher", "bgpx.tasks.ip_geo.refresher")


@dataclass(frozen=True)
class SourceFingerprint:
    """Lightweight source fingerprint used for change detection."""

    inode: int
    mtime_ns: int


PublishSnapshotCallable = Callable[[IpGeolocationReadResult, dict[str, object]], None]
SnapshotEquivalentCallable = Callable[[IpGeolocationReadResult], bool]
ApplySnapshotDeltaCallable = Callable[[IpGeolocationReadResult, dict[str, object]], bool]


class _ReaderAdapterProtocol(Protocol):
    """Protocol for dataset readers used by refresher."""

    def read_records(self) -> IpGeolocationReadResult: ...


class IpGeolocationDataRefresher:
    """Poll source metadata and publish fresh snapshots when source changes."""

    def __init__(
        self,
        *,
        publish_snapshot: PublishSnapshotCallable,
        is_snapshot_equivalent: SnapshotEquivalentCallable | None = None,
        apply_snapshot_delta: ApplySnapshotDeltaCallable | None = None,
        adapter: _ReaderAdapterProtocol | None = None,
        source_path: str | os.PathLike[str] = DATASET_PATH,
        debounce_seconds: float = 0.5,
        stat_func: Callable[[str | os.PathLike[str]], Any] = os.stat,
        sleep_func: Callable[[float], None] = time.sleep,
        publish_chunk_size: int = 50_000,
    ) -> None:
        self._publish_snapshot = publish_snapshot
        self._is_snapshot_equivalent = is_snapshot_equivalent
        self._apply_snapshot_delta = apply_snapshot_delta
        self._adapter = adapter or IpGeolocationIpinfoJsonFileReaderAdapter()
        self._source_path = source_path
        self._debounce_seconds = debounce_seconds
        self._stat_func = stat_func
        self._sleep_func = sleep_func
        self._publish_chunk_size = publish_chunk_size

        self._last_fingerprint: SourceFingerprint | None = None
        self.last_refresh_error: str | None = None
        self.last_refresh_attempt_at: datetime | None = None
        self.last_refresh_succeeded_at: datetime | None = None
        self.refresh_attempt_count: int = 0
        self.refresh_success_count: int = 0
        self.refresh_failure_count: int = 0

    def run_once(self) -> None:
        """Run one poll cycle and publish when source change is detected."""
        event_logger.log("poll_started", "DEBUG", "IP geolocation refresher poll tick started (path=%s)", self._source_path)
        current = self._read_source_fingerprint()
        if self._handle_missing_source(current):
            event_logger.log("source_missing", "DEBUG", "IP geolocation refresher poll tick skipped; source missing")
            return
        if current is None:
            event_logger.log(
                "source_fingerprint_unavailable",
                "DEBUG",
                "IP geolocation refresher poll tick skipped; source fingerprint unavailable",
            )
            return

        if self._is_unchanged(current):
            event_logger.log(
                "poll_unchanged",
                "DEBUG",
                "IP geolocation refresher poll tick unchanged (inode=%s, mtime_ns=%s)",
                current.inode,
                current.mtime_ns,
            )
            return

        confirmed = self._confirm_change_after_debounce(current)
        if confirmed is None:
            event_logger.log(
                "debounce_skipped",
                "DEBUG",
                "IP geolocation refresher poll tick skipped after debounce confirmation",
            )
            return

        self._reload_and_publish(confirmed)

    def _handle_missing_source(self, current: SourceFingerprint | None) -> bool:
        if current is not None:
            return False
        return True

    def _is_unchanged(self, current: SourceFingerprint) -> bool:
        if self._last_fingerprint is None or current != self._last_fingerprint:
            return False
        return True

    def _confirm_change_after_debounce(
        self,
        current: SourceFingerprint,
    ) -> SourceFingerprint | None:
        if self._last_fingerprint is None or self._debounce_seconds <= 0:
            return current

        self._sleep_func(self._debounce_seconds)
        confirmed = self._read_source_fingerprint()
        if confirmed is None or confirmed == self._last_fingerprint:
            return None

        return confirmed

    def _reload_and_publish(self, next_fingerprint: SourceFingerprint) -> None:
        """Rebuild dataset snapshot and publish only on successful parse/build."""
        refresh_started_at = time.monotonic()
        self.refresh_attempt_count += 1
        self.last_refresh_attempt_at = datetime.now(UTC)
        event_logger.log(
            "source_change_detected",
            "INFO",
            "IP geolocation source change detected; refreshing snapshot "
            "(path=%s, inode=%s, mtime_ns=%s)",
            self._source_path,
            next_fingerprint.inode,
            next_fingerprint.mtime_ns,
        )

        try:
            read_result = self._adapter.read_records()
            if self._try_skip_for_equivalent_snapshot(read_result, next_fingerprint):
                return

            if self._try_apply_delta(read_result, next_fingerprint):
                return

            last_read_result = self._publish_refresh_result(
                read_result,
                next_fingerprint,
                refresh_started_at,
            )

            if last_read_result is None:
                return

            self._mark_refresh_success(next_fingerprint)
            event_logger.log(
                "refresh_succeeded",
                "INFO",
                "IP geolocation snapshot refresh succeeded "
                "(total_lines=%s, malformed_lines=%s, success_count=%s)",
                last_read_result.total_lines,
                last_read_result.malformed_lines,
                self.refresh_success_count,
            )
        except Exception as exc:
            self.last_refresh_error = str(exc) or exc.__class__.__name__
            self.refresh_failure_count += 1
            event_logger.exception(
                "refresh_failed",
                "IP geolocation snapshot refresh failed (failure_count=%s): %s",
                self.refresh_failure_count,
                self.last_refresh_error,
            )

    def _try_skip_for_equivalent_snapshot(
        self,
        read_result: IpGeolocationReadResult,
        next_fingerprint: SourceFingerprint,
    ) -> bool:
        if self._is_snapshot_equivalent is None or self._last_fingerprint is None:
            return False
        if not self._is_snapshot_equivalent(read_result):
            return False

        self._mark_refresh_success(next_fingerprint)
        event_logger.log(
            "refresh_skipped_equivalent",
            "INFO",
            "IP geolocation refresh skipped; source content unchanged "
            "(total_lines=%s, malformed_lines=%s, success_count=%s)",
            read_result.total_lines,
            read_result.malformed_lines,
            self.refresh_success_count,
        )
        return True

    def _try_apply_delta(
        self,
        read_result: IpGeolocationReadResult,
        next_fingerprint: SourceFingerprint,
    ) -> bool:
        if self._apply_snapshot_delta is None or self._last_fingerprint is None:
            return False

        delta_metadata = self._build_publish_metadata(read_result, next_fingerprint, is_final_chunk=True)
        if not self._apply_snapshot_delta(read_result, delta_metadata):
            return False

        self._mark_refresh_success(next_fingerprint)
        event_logger.log(
            "refresh_applied_delta",
            "INFO",
            "IP geolocation snapshot refresh applied as delta "
            "(total_lines=%s, malformed_lines=%s, success_count=%s)",
            read_result.total_lines,
            read_result.malformed_lines,
            self.refresh_success_count,
        )
        return True

    def _publish_refresh_result(
        self,
        read_result: IpGeolocationReadResult,
        next_fingerprint: SourceFingerprint,
        refresh_started_at: float,
    ) -> IpGeolocationReadResult | None:
        iter_reader = getattr(self._adapter, "iter_read_results", None)
        if callable(iter_reader):
            return self._publish_chunked_results(iter_reader, next_fingerprint, refresh_started_at)

        self._publish_single_result(read_result, next_fingerprint, refresh_started_at)
        return read_result

    def _publish_chunked_results(
        self,
        iter_reader: Callable[..., object],
        next_fingerprint: SourceFingerprint,
        refresh_started_at: float,
    ) -> IpGeolocationReadResult | None:
        chunk_results = cast(
            Iterator[IpGeolocationReadResult],
            iter_reader(chunk_size=self._publish_chunk_size),
        )
        chunk_index = 0
        last_read_result: IpGeolocationReadResult | None = None
        current_chunk = next(chunk_results, None)

        while current_chunk is not None:
            next_chunk = next(chunk_results, None)
            chunk_index += 1
            is_final_chunk = next_chunk is None
            metadata = self._build_publish_metadata(
                current_chunk,
                next_fingerprint,
                is_final_chunk=is_final_chunk,
            )
            self._publish_snapshot(current_chunk, metadata)
            self._log_chunk_publish(
                chunk_index=chunk_index,
                is_final_chunk=is_final_chunk,
                read_result=current_chunk,
                refresh_started_at=refresh_started_at,
            )
            last_read_result = current_chunk
            current_chunk = next_chunk

        return last_read_result

    def _publish_single_result(
        self,
        read_result: IpGeolocationReadResult,
        next_fingerprint: SourceFingerprint,
        refresh_started_at: float,
    ) -> None:
        metadata = self._build_publish_metadata(read_result, next_fingerprint, is_final_chunk=True)
        self._publish_snapshot(read_result, metadata)
        self._log_chunk_publish(
            chunk_index=1,
            is_final_chunk=True,
            read_result=read_result,
            refresh_started_at=refresh_started_at,
            chunk_total=1,
        )

    def _build_publish_metadata(
        self,
        read_result: IpGeolocationReadResult,
        next_fingerprint: SourceFingerprint,
        *,
        is_final_chunk: bool,
    ) -> dict[str, object]:
        return {
            "source_fingerprint": next_fingerprint,
            "total_lines": read_result.total_lines,
            "malformed_lines": read_result.malformed_lines,
            "is_final_chunk": is_final_chunk,
        }

    def _log_chunk_publish(
        self,
        *,
        chunk_index: int,
        is_final_chunk: bool,
        read_result: IpGeolocationReadResult,
        refresh_started_at: float,
        chunk_total: int | None = None,
    ) -> None:
        secs_elapsed = time.monotonic() - refresh_started_at
        chunk_value = chunk_index if chunk_total is None else f"{chunk_index}/{chunk_total}"
        event_logger.log(
            "chunk_published",
            "DEBUG",
            "IP geolocation refresh chunk published "
            "(chunk=%s, is_final_chunk=%s, total_lines=%s, loaded_records=%s, malformed_lines=%s, secs_elapsed=%.2f)",
            chunk_value,
            is_final_chunk,
            read_result.total_lines,
            len(read_result.records),
            read_result.malformed_lines,
            secs_elapsed,
        )

    def _mark_refresh_success(self, next_fingerprint: SourceFingerprint) -> None:
        self._last_fingerprint = next_fingerprint
        self.last_refresh_error = None
        self.last_refresh_succeeded_at = datetime.now(UTC)
        self.refresh_success_count += 1

    def _read_source_fingerprint(self) -> SourceFingerprint | None:
        """Read source metadata fingerprint for change detection."""
        try:
            stat_result = self._stat_func(self._source_path)
        except FileNotFoundError:
            return None

        return SourceFingerprint(inode=stat_result.st_ino, mtime_ns=stat_result.st_mtime_ns)


__all__ = [
    "ApplySnapshotDeltaCallable",
    "IpGeolocationDataRefresher",
    "PublishSnapshotCallable",
    "SnapshotEquivalentCallable",
    "SourceFingerprint",
]
