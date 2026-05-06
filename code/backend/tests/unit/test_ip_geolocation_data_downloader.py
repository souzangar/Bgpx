"""Unit tests for dedicated IP geolocation .gz downloader/watcher behavior."""

from __future__ import annotations

import gzip
import logging
from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.ip_geolocation.ip_geolocation_data_downloader import (  # noqa: E402
    IpGeolocationDataDownloader,
)


class _FakeStat:
    def __init__(self, inode: int, mtime_ns: int) -> None:
        self.st_ino = inode
        self.st_mtime_ns = mtime_ns


def _write_gz(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wb") as handle:
        handle.write(content.encode("utf-8"))


def test_downloader_skips_when_fingerprint_unchanged(tmp_path: Path) -> None:
    """Second run with unchanged .gz fingerprint should not trigger sync."""
    gz_path = tmp_path / "ipinfo_lite.json.gz"
    working_path = tmp_path / "ipinfo_lite.json"
    temp_path = tmp_path / "ipinfo_lite.tmp.json"
    _write_gz(gz_path, '{"a":1}\n')
    working_path.write_text('{"a":0}\n', encoding="utf-8")

    fingerprints = [_FakeStat(10, 1000), _FakeStat(10, 1000)]

    def _stat_func(_path: object) -> _FakeStat:
        return fingerprints.pop(0)

    downloader = IpGeolocationDataDownloader(
        gz_source_path=gz_path,
        working_dataset_path=working_path,
        temp_dataset_path=temp_path,
        stat_func=_stat_func,
        sleep_func=lambda _seconds: None,
    )

    downloader.run_once()
    first_content = working_path.read_text(encoding="utf-8")
    downloader.run_once()
    second_content = working_path.read_text(encoding="utf-8")

    assert downloader.sync_attempt_count == 1
    assert first_content == '{"a":1}\n'
    assert second_content == '{"a":1}\n'
    assert temp_path.exists() is False


def test_downloader_replaces_working_file_when_content_differs(tmp_path: Path) -> None:
    """Changed .gz content should replace working JSON and cleanup static temp file."""
    gz_path = tmp_path / "ipinfo_lite.json.gz"
    working_path = tmp_path / "ipinfo_lite.json"
    temp_path = tmp_path / "ipinfo_lite.tmp.json"
    _write_gz(gz_path, '{"a":2}\n')
    working_path.write_text('{"a":1}\n', encoding="utf-8")

    downloader = IpGeolocationDataDownloader(
        gz_source_path=gz_path,
        working_dataset_path=working_path,
        temp_dataset_path=temp_path,
        stat_func=lambda _path: _FakeStat(10, 1000),
        sleep_func=lambda _seconds: None,
    )

    downloader.run_once()

    assert working_path.read_text(encoding="utf-8") == '{"a":2}\n'
    assert temp_path.exists() is False
    assert downloader.sync_attempt_count == 1
    assert downloader.sync_success_count == 1


def test_downloader_keeps_working_file_when_content_is_same(tmp_path: Path) -> None:
    """Identical extracted content should not alter working file and should cleanup temp file."""
    gz_path = tmp_path / "ipinfo_lite.json.gz"
    working_path = tmp_path / "ipinfo_lite.json"
    temp_path = tmp_path / "ipinfo_lite.tmp.json"
    _write_gz(gz_path, '{"a":1}\n')
    working_path.write_text('{"a":1}\n', encoding="utf-8")

    downloader = IpGeolocationDataDownloader(
        gz_source_path=gz_path,
        working_dataset_path=working_path,
        temp_dataset_path=temp_path,
        stat_func=lambda _path: _FakeStat(10, 1000),
        sleep_func=lambda _seconds: None,
    )

    downloader.run_once()

    assert working_path.read_text(encoding="utf-8") == '{"a":1}\n'
    assert temp_path.exists() is False
    assert downloader.sync_success_count == 1


def test_downloader_handles_missing_gz_as_noop(tmp_path: Path) -> None:
    """Missing .gz source should return silently without failed sync accounting."""
    gz_path = tmp_path / "missing.json.gz"
    downloader = IpGeolocationDataDownloader(
        gz_source_path=gz_path,
        working_dataset_path=tmp_path / "ipinfo_lite.json",
        temp_dataset_path=tmp_path / "ipinfo_lite.tmp.json",
        stat_func=lambda _path: (_ for _ in ()).throw(FileNotFoundError()),
        sleep_func=lambda _seconds: None,
    )

    downloader.run_once()

    assert downloader.sync_attempt_count == 0
    assert downloader.sync_failure_count == 0


def test_downloader_cleans_static_temp_file_on_failure(tmp_path: Path) -> None:
    """Temp file must be deleted even when extraction/comparison flow fails."""
    gz_path = tmp_path / "ipinfo_lite.json.gz"
    working_path = tmp_path / "ipinfo_lite.json"
    temp_path = tmp_path / "ipinfo_lite.tmp.json"
    _write_gz(gz_path, '{"a":1}\n')

    downloader = IpGeolocationDataDownloader(
        gz_source_path=gz_path,
        working_dataset_path=working_path,
        temp_dataset_path=temp_path,
        stat_func=lambda _path: _FakeStat(10, 1000),
        sleep_func=lambda _seconds: None,
    )

    def _raise_after_extract() -> bool:
        raise RuntimeError("compare failed")

    downloader._should_replace_working_dataset = _raise_after_extract  # type: ignore[method-assign]
    downloader.run_once()

    assert downloader.sync_failure_count == 1
    assert downloader.last_sync_error == "compare failed"
    assert temp_path.exists() is False


def test_downloader_verbose_logs_only_refresh_events(monkeypatch, caplog, tmp_path: Path) -> None:
    """Verbose mode should emit event-level logs only during sync."""
    monkeypatch.setenv("BGPX_VERBOSE", "1")
    gz_path = tmp_path / "ipinfo_lite.json.gz"
    working_path = tmp_path / "ipinfo_lite.json"
    temp_path = tmp_path / "ipinfo_lite.tmp.json"
    _write_gz(gz_path, '{"a":2}\n')
    working_path.write_text('{"a":1}\n', encoding="utf-8")

    downloader = IpGeolocationDataDownloader(
        gz_source_path=gz_path,
        working_dataset_path=working_path,
        temp_dataset_path=temp_path,
        stat_func=lambda _path: _FakeStat(10, 1000),
        sleep_func=lambda _seconds: None,
    )

    with caplog.at_level(logging.INFO):
        downloader.run_once()

    messages = [record.getMessage() for record in caplog.records]
    assert any("source change detected" in message for message in messages)
    assert any("replacing working dataset" in message for message in messages)
    assert all("extracting gzip to temp" not in message for message in messages)
    assert all("compare completed" not in message for message in messages)
    assert all("sync succeeded" not in message for message in messages)
    assert all("temp cleanup completed" not in message for message in messages)


def test_downloader_no_verbose_logs_when_verbose_disabled(monkeypatch, caplog, tmp_path: Path) -> None:
    """Downloader should not emit verbose logs when BGPX_VERBOSE is disabled."""
    monkeypatch.setenv("BGPX_VERBOSE", "0")
    gz_path = tmp_path / "ipinfo_lite.json.gz"
    working_path = tmp_path / "ipinfo_lite.json"
    temp_path = tmp_path / "ipinfo_lite.tmp.json"
    _write_gz(gz_path, '{"a":2}\n')
    working_path.write_text('{"a":1}\n', encoding="utf-8")

    downloader = IpGeolocationDataDownloader(
        gz_source_path=gz_path,
        working_dataset_path=working_path,
        temp_dataset_path=temp_path,
        stat_func=lambda _path: _FakeStat(10, 1000),
        sleep_func=lambda _seconds: None,
    )

    with caplog.at_level(logging.INFO):
        downloader.run_once()

    assert caplog.records == []


def test_downloader_no_skip_logs_even_when_verbose_enabled(monkeypatch, caplog, tmp_path: Path) -> None:
    """Verbose mode should not emit any 'skipped' downloader logs."""
    monkeypatch.setenv("BGPX_VERBOSE", "1")
    gz_path = tmp_path / "ipinfo_lite.json.gz"
    _write_gz(gz_path, '{"a":2}\n')

    fingerprints = [_FakeStat(10, 1000), _FakeStat(10, 1000)]

    def _stat_func(_path: object) -> _FakeStat:
        return fingerprints.pop(0)

    downloader = IpGeolocationDataDownloader(
        gz_source_path=gz_path,
        working_dataset_path=tmp_path / "ipinfo_lite.json",
        temp_dataset_path=tmp_path / "ipinfo_lite.tmp.json",
        stat_func=_stat_func,
        sleep_func=lambda _seconds: None,
    )

    with caplog.at_level(logging.INFO):
        downloader.run_once()
        downloader.run_once()

    messages = [record.getMessage() for record in caplog.records]
    assert not any("IPinfo .gz downloader skipped" in message for message in messages)
