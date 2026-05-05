"""Dedicated .gz watcher/downloader-style service for IP geolocation dataset replacement."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import filecmp
import gzip
import logging
import os
from pathlib import Path
import shutil
import time
from typing import Any, Callable


GZ_DATASET_PATH = Path("code/backend/data/ip_geolocation/ipinfo_lite.json.gz")
WORKING_DATASET_PATH = Path("code/backend/data/ip_geolocation/ipinfo_lite.json")
TEMP_DATASET_PATH = Path("code/backend/data/ip_geolocation/ipinfo_lite.tmp.json")
VERBOSE_ENV = "BGPX_VERBOSE"
_TRUTHY_VALUES = {"1", "true", "yes", "on"}
logger = logging.getLogger("uvicorn.error")


def _is_verbose_enabled() -> bool:
    """Return whether verbose logging is enabled from runtime environment."""
    return os.getenv(VERBOSE_ENV, "0").strip().lower() in _TRUTHY_VALUES


@dataclass(frozen=True)
class SourceFingerprint:
    """Lightweight source fingerprint used for .gz change detection."""

    inode: int
    mtime_ns: int


class IpGeolocationDataDownloader:
    """Watch .gz source changes and conditionally replace working JSON dataset."""

    def __init__(
        self,
        *,
        gz_source_path: Path = GZ_DATASET_PATH,
        working_dataset_path: Path = WORKING_DATASET_PATH,
        temp_dataset_path: Path = TEMP_DATASET_PATH,
        debounce_seconds: float = 0.5,
        stat_func: Callable[[str | os.PathLike[str]], Any] = os.stat,
        sleep_func: Callable[[float], None] = time.sleep,
    ) -> None:
        self._gz_source_path = gz_source_path
        self._working_dataset_path = working_dataset_path
        self._temp_dataset_path = temp_dataset_path
        self._debounce_seconds = debounce_seconds
        self._stat_func = stat_func
        self._sleep_func = sleep_func
        self._verbose = _is_verbose_enabled()

        self._last_fingerprint: SourceFingerprint | None = None
        self.last_sync_error: str | None = None
        self.last_sync_attempt_at: datetime | None = None
        self.last_sync_succeeded_at: datetime | None = None
        self.sync_attempt_count: int = 0
        self.sync_success_count: int = 0
        self.sync_failure_count: int = 0

    def run_once(self) -> None:
        """Run one poll cycle and sync working dataset when .gz source changes."""
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

        if self._verbose:
            logger.info(
                "IPinfo .gz downloader source change detected (path=%s, inode=%s, mtime_ns=%s)",
                self._gz_source_path,
                current.inode,
                current.mtime_ns,
            )

        self._extract_compare_and_replace(current)

    def _extract_compare_and_replace(self, next_fingerprint: SourceFingerprint) -> None:
        self.sync_attempt_count += 1
        self.last_sync_attempt_at = datetime.now(UTC)

        try:
            if self._verbose:
                logger.info(
                    "IPinfo .gz downloader extracting gzip to temp (source=%s, temp=%s)",
                    self._gz_source_path,
                    self._temp_dataset_path,
                )
            self._extract_gz_to_temp_json()
            should_replace = self._should_replace_working_dataset()
            if self._verbose:
                logger.info(
                    "IPinfo .gz downloader compare completed (working=%s, temp=%s, should_replace=%s)",
                    self._working_dataset_path,
                    self._temp_dataset_path,
                    should_replace,
                )

            if should_replace:
                if self._verbose:
                    logger.info(
                        "IPinfo .gz downloader replacing working dataset (working=%s)",
                        self._working_dataset_path,
                    )
                self._replace_working_dataset_from_temp()
            elif self._verbose:
                logger.info(
                    "IPinfo .gz downloader no replace required (working already up-to-date path=%s)",
                    self._working_dataset_path,
                )

            self._last_fingerprint = next_fingerprint
            self.last_sync_error = None
            self.last_sync_succeeded_at = datetime.now(UTC)
            self.sync_success_count += 1
            if self._verbose:
                logger.info(
                    "IPinfo .gz downloader sync succeeded (success_count=%s)",
                    self.sync_success_count,
                )
        except Exception as exc:
            self.last_sync_error = str(exc) or exc.__class__.__name__
            self.sync_failure_count += 1
            if self._verbose:
                logger.exception(
                    "IPinfo .gz downloader sync failed (failure_count=%s): %s",
                    self.sync_failure_count,
                    self.last_sync_error,
                )
        finally:
            self._delete_temp_file_if_exists()
            if self._verbose:
                logger.info(
                    "IPinfo .gz downloader temp cleanup completed (temp=%s)",
                    self._temp_dataset_path,
                )

    def _extract_gz_to_temp_json(self) -> None:
        self._temp_dataset_path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(self._gz_source_path, "rb") as gz_file:
            with self._temp_dataset_path.open("wb") as temp_file:
                shutil.copyfileobj(gz_file, temp_file)

    def _should_replace_working_dataset(self) -> bool:
        if not self._working_dataset_path.exists():
            return True

        return not filecmp.cmp(
            self._temp_dataset_path,
            self._working_dataset_path,
            shallow=False,
        )

    def _replace_working_dataset_from_temp(self) -> None:
        self._working_dataset_path.parent.mkdir(parents=True, exist_ok=True)
        with self._temp_dataset_path.open("rb") as source_handle:
            with self._working_dataset_path.open("wb") as target_handle:
                shutil.copyfileobj(source_handle, target_handle)

    def _delete_temp_file_if_exists(self) -> None:
        if self._temp_dataset_path.exists():
            self._temp_dataset_path.unlink()

    def _read_source_fingerprint(self) -> SourceFingerprint | None:
        try:
            stat_result = self._stat_func(self._gz_source_path)
        except FileNotFoundError:
            return None

        return SourceFingerprint(inode=stat_result.st_ino, mtime_ns=stat_result.st_mtime_ns)


__all__ = [
    "GZ_DATASET_PATH",
    "TEMP_DATASET_PATH",
    "WORKING_DATASET_PATH",
    "IpGeolocationDataDownloader",
    "SourceFingerprint",
]
