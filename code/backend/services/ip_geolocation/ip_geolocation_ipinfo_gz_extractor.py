"""IP geolocation extractor with event-based, JSON-configured logging.

Logging model (human + AI agent guidance)
-----------------------------------------
- This module emits logs through `event_logger` (see `get_component_event_logger`).
- Runtime logging behavior is configured in:
  `code/backend/data/configs/logging_config.json`
- Component key for this file: `ip_geo_ipinfo_gz_extractor`

Important rules when editing/adding logs
---------------------------------------
1) Every `event_logger.log("<event_id>", ...)` / `event_logger.exception("<event_id>", ...)`
   should have a matching event entry in `logging_config.json` under:
   `components.ip_geo_ipinfo_gz_extractor.events`.
2) If you add a new event ID in code, update JSON in the same change.
3) Keep event IDs stable and descriptive (for example: `source_change_detected`, `sync_failed`).

Hot-reload behavior
-------------------
- Event-level config is reloaded in-process when `logging_config.json` changes.
- No backend process restart is required.
- New JSON values apply to the next logging cycle/event emission.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import filecmp
import gzip
import json
import os
from pathlib import Path
import shutil
import time
from typing import Any, Callable

from services.logging.logging_service import get_component_event_logger


GZ_DATASET_PATH = Path("code/backend/data/ip_geolocation/ipinfo_lite.json.gz")
WORKING_DATASET_PATH = Path("code/backend/data/ip_geolocation/ipinfo_lite.json")
TEMP_DATASET_PATH = Path("code/backend/data/ip_geolocation/ipinfo_lite.tmp.json")
event_logger = get_component_event_logger("ip_geo_ipinfo_gz_extractor", "bgpx.tasks.ip_geo.ipinfo_gz_extractor")

_LOCALHOST_OVERRIDE_RECORD = {
    "network": "127.0.0.0/30",
    "country": "Your PC",
    "country_code": "YP",
    "continent": "Planet Earth",
    "continent_code": "PE",
    "asn": "AS_198",
    "as_name": "BGPX Team",
    "as_domain": "bgpx.net",
}
_LOCALHOST_OVERRIDE_LINE = json.dumps(_LOCALHOST_OVERRIDE_RECORD, ensure_ascii=False)


@dataclass(frozen=True)
class SourceFingerprint:
    """Lightweight source fingerprint used for .gz change detection."""

    inode: int
    mtime_ns: int


class IpGeolocationIpinfoGzExtractor:
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

        self._last_fingerprint: SourceFingerprint | None = None
        self.last_sync_error: str | None = None
        self.last_sync_attempt_at: datetime | None = None
        self.last_sync_succeeded_at: datetime | None = None
        self.sync_attempt_count: int = 0
        self.sync_success_count: int = 0
        self.sync_failure_count: int = 0

    def run_once(self) -> None:
        """Run one poll cycle and sync working dataset when .gz source changes."""
        event_logger.log("poll_started", "DEBUG", "IPinfo .gz extractor poll tick started (path=%s)", self._gz_source_path)
        current = self._read_source_fingerprint()
        if current is None:
            event_logger.log("source_missing", "DEBUG", "IPinfo .gz extractor poll tick skipped; source missing")
            return

        if self._last_fingerprint is not None and current == self._last_fingerprint:
            event_logger.log(
                "poll_unchanged",
                "DEBUG",
                "IPinfo .gz extractor poll tick unchanged (inode=%s, mtime_ns=%s)",
                current.inode,
                current.mtime_ns,
            )
            return

        if self._last_fingerprint is not None and self._debounce_seconds > 0:
            self._sleep_func(self._debounce_seconds)
            confirmed = self._read_source_fingerprint()
            if confirmed is None or confirmed == self._last_fingerprint:
                event_logger.log(
                    "debounce_skipped",
                    "DEBUG",
                    "IPinfo .gz extractor poll tick skipped after debounce confirmation",
                )
                return
            current = confirmed

        event_logger.log(
            "source_change_detected",
            "INFO",
            "IPinfo .gz extractor source change detected (path=%s, inode=%s, mtime_ns=%s)",
            self._gz_source_path,
            current.inode,
            current.mtime_ns,
        )

        self._extract_compare_and_replace(current)

    def _extract_compare_and_replace(self, next_fingerprint: SourceFingerprint) -> None:
        self.sync_attempt_count += 1
        self.last_sync_attempt_at = datetime.now(UTC)

        try:
            self._extract_gz_to_temp_json()
            should_replace = self._should_replace_working_dataset()

            if should_replace:
                event_logger.log(
                    "replace_working_dataset",
                    "INFO",
                    "IPinfo .gz extractor replacing working dataset (working=%s)",
                    self._working_dataset_path,
                )
                self._replace_working_dataset_from_temp()
            else:
                event_logger.log(
                    "keep_working_dataset",
                    "DEBUG",
                    "IPinfo .gz extractor extracted content unchanged; keeping working dataset",
                )

            self._last_fingerprint = next_fingerprint
            self.last_sync_error = None
            self.last_sync_succeeded_at = datetime.now(UTC)
            self.sync_success_count += 1
        except Exception as exc:
            self.last_sync_error = str(exc) or exc.__class__.__name__
            self.sync_failure_count += 1
            event_logger.exception(
                "sync_failed",
                "IPinfo .gz extractor sync failed (failure_count=%s): %s",
                self.sync_failure_count,
                self.last_sync_error,
            )
        finally:
            self._delete_temp_file_if_exists()

    def _extract_gz_to_temp_json(self) -> None:
        self._temp_dataset_path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(self._gz_source_path, "rb") as gz_file:
            with self._temp_dataset_path.open("wb") as temp_file:
                shutil.copyfileobj(gz_file, temp_file)
        self._ensure_localhost_override_in_temp_json()

    def _ensure_localhost_override_in_temp_json(self) -> None:
        """Ensure custom localhost override line exists at top of extracted NDJSON."""
        content = self._temp_dataset_path.read_text(encoding="utf-8")
        lines = content.splitlines()

        if not lines:
            self._temp_dataset_path.write_text(f"{_LOCALHOST_OVERRIDE_LINE}\n", encoding="utf-8")
            event_logger.log(
                "localhost_override_added",
                "INFO",
                "IPinfo .gz extractor added localhost override as first dataset line",
            )
            return

        if lines[0].strip() == _LOCALHOST_OVERRIDE_LINE:
            event_logger.log(
                "localhost_override_already_present",
                "DEBUG",
                "IPinfo .gz extractor verified localhost override already exists as first line",
            )
            return

        filtered_lines = [line for line in lines if line.strip() != _LOCALHOST_OVERRIDE_LINE]
        rebuilt_content = "\n".join([_LOCALHOST_OVERRIDE_LINE, *filtered_lines]) + "\n"
        self._temp_dataset_path.write_text(rebuilt_content, encoding="utf-8")
        event_logger.log(
            "localhost_override_added",
            "INFO",
            "IPinfo .gz extractor prepended localhost override to dataset",
        )

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
    "IpGeolocationIpinfoGzExtractor",
    "SourceFingerprint",
]
