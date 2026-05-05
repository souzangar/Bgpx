"""Domain refresher for IP geolocation source-change driven snapshot updates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import logging
import os
import time
from collections.abc import Iterator
from typing import Any, Callable, Protocol, cast

from infra.ip_geolocation import (
    DATASET_PATH,
    IpGeolocationIpinfoJsonFileReaderAdapter,
    IpGeolocationReadResult,
)


VERBOSE_ENV = "BGPX_VERBOSE"
_TRUTHY_VALUES = {"1", "true", "yes", "on"}
logger = logging.getLogger("uvicorn.error")


def _is_verbose_enabled() -> bool:
    """Return whether verbose logging is enabled from runtime environment."""
    return os.getenv(VERBOSE_ENV, "0").strip().lower() in _TRUTHY_VALUES


@dataclass(frozen=True)
class SourceFingerprint:
    """Lightweight source fingerprint used for change detection."""

    inode: int
    mtime_ns: int


PublishSnapshotCallable = Callable[[IpGeolocationReadResult, dict[str, object]], None]


class _ReaderAdapterProtocol(Protocol):
    """Protocol for dataset readers used by refresher."""

    def read_records(self) -> IpGeolocationReadResult: ...


class IpGeolocationDataRefresher:
    """Poll source metadata and publish fresh snapshots when source changes."""

    def __init__(
        self,
        *,
        publish_snapshot: PublishSnapshotCallable,
        adapter: _ReaderAdapterProtocol | None = None,
        source_path: str | os.PathLike[str] = DATASET_PATH,
        debounce_seconds: float = 0.5,
        stat_func: Callable[[str | os.PathLike[str]], Any] = os.stat,
        sleep_func: Callable[[float], None] = time.sleep,
        publish_chunk_size: int = 5_000,
    ) -> None:
        self._publish_snapshot = publish_snapshot
        self._adapter = adapter or IpGeolocationIpinfoJsonFileReaderAdapter()
        self._source_path = source_path
        self._debounce_seconds = debounce_seconds
        self._stat_func = stat_func
        self._sleep_func = sleep_func
        self._publish_chunk_size = publish_chunk_size
        self._verbose = _is_verbose_enabled()

        self._last_fingerprint: SourceFingerprint | None = None
        self.last_refresh_error: str | None = None
        self.last_refresh_attempt_at: datetime | None = None
        self.last_refresh_succeeded_at: datetime | None = None
        self.refresh_attempt_count: int = 0
        self.refresh_success_count: int = 0
        self.refresh_failure_count: int = 0

    def run_once(self) -> None:
        """Run one poll cycle and publish when source change is detected."""
        current = self._read_source_fingerprint()
        if current is None:
            return

        if self._last_fingerprint is not None and current == self._last_fingerprint:
            return

        if self._last_fingerprint is not None and self._debounce_seconds > 0:
            self._sleep_func(self._debounce_seconds)
            confirmed = self._read_source_fingerprint()
            if confirmed is None or confirmed == self._last_fingerprint:
                return
            current = confirmed

        self._reload_and_publish(current)

    def _reload_and_publish(self, next_fingerprint: SourceFingerprint) -> None:
        """Rebuild dataset snapshot and publish only on successful parse/build."""
        refresh_started_at = time.monotonic()
        self.refresh_attempt_count += 1
        self.last_refresh_attempt_at = datetime.now(UTC)

        if self._verbose:
            logger.info(
                "IP geolocation source change detected; refreshing snapshot "
                "(path=%s, inode=%s, mtime_ns=%s)",
                self._source_path,
                next_fingerprint.inode,
                next_fingerprint.mtime_ns,
            )

        try:
            last_read_result: IpGeolocationReadResult | None = None

            iter_reader = getattr(self._adapter, "iter_read_results", None)
            if callable(iter_reader):
                chunk_results = cast(Iterator[IpGeolocationReadResult], iter_reader(chunk_size=self._publish_chunk_size))
                chunk_index = 0
                current_chunk = next(chunk_results, None)
                while current_chunk is not None:
                    next_chunk = next(chunk_results, None)
                    chunk_index += 1
                    is_final_chunk = next_chunk is None
                    metadata = {
                        "source_fingerprint": next_fingerprint,
                        "total_lines": current_chunk.total_lines,
                        "malformed_lines": current_chunk.malformed_lines,
                        "is_final_chunk": is_final_chunk,
                    }
                    self._publish_snapshot(current_chunk, metadata)
                    if self._verbose:
                        secs_elapsed = time.monotonic() - refresh_started_at
                        logger.info(
                            "IP geolocation refresh chunk published "
                            "(chunk=%s, is_final_chunk=%s, total_lines=%s, loaded_records=%s, malformed_lines=%s, secs_elapsed=%.2f)",
                            chunk_index,
                            is_final_chunk,
                            current_chunk.total_lines,
                            len(current_chunk.records),
                            current_chunk.malformed_lines,
                            secs_elapsed,
                        )
                    last_read_result = current_chunk
                    current_chunk = next_chunk
            else:
                read_result = self._adapter.read_records()
                metadata = {
                    "source_fingerprint": next_fingerprint,
                    "total_lines": read_result.total_lines,
                    "malformed_lines": read_result.malformed_lines,
                    "is_final_chunk": True,
                }
                self._publish_snapshot(read_result, metadata)
                if self._verbose:
                    secs_elapsed = time.monotonic() - refresh_started_at
                    logger.info(
                        "IP geolocation refresh chunk published "
                        "(chunk=%s/%s, is_final_chunk=%s, total_lines=%s, loaded_records=%s, malformed_lines=%s, secs_elapsed=%.2f)",
                        1,
                        1,
                        True,
                        read_result.total_lines,
                        len(read_result.records),
                        read_result.malformed_lines,
                        secs_elapsed,
                    )
                last_read_result = read_result

            if last_read_result is None:
                return

            self._last_fingerprint = next_fingerprint
            self.last_refresh_error = None
            self.last_refresh_succeeded_at = datetime.now(UTC)
            self.refresh_success_count += 1
            if self._verbose:
                logger.info(
                    "IP geolocation snapshot refresh succeeded "
                    "(total_lines=%s, malformed_lines=%s, success_count=%s)",
                    last_read_result.total_lines,
                    last_read_result.malformed_lines,
                    self.refresh_success_count,
                )
        except Exception as exc:
            self.last_refresh_error = str(exc) or exc.__class__.__name__
            self.refresh_failure_count += 1
            if self._verbose:
                logger.exception(
                    "IP geolocation snapshot refresh failed (failure_count=%s): %s",
                    self.refresh_failure_count,
                    self.last_refresh_error,
                )

    def _read_source_fingerprint(self) -> SourceFingerprint | None:
        """Read source metadata fingerprint for change detection."""
        try:
            stat_result = self._stat_func(self._source_path)
        except FileNotFoundError:
            return None

        return SourceFingerprint(inode=stat_result.st_ino, mtime_ns=stat_result.st_mtime_ns)


__all__ = [
    "IpGeolocationDataRefresher",
    "PublishSnapshotCallable",
    "SourceFingerprint",
]
