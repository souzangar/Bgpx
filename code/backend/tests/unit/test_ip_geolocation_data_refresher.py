"""Unit tests for IP geolocation data refresher behavior."""

from __future__ import annotations

import logging
from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from infra.ip_geolocation import IpGeolocationReadResult
from services.ip_geolocation.ip_geolocation_data_refresher import IpGeolocationDataRefresher


class _FakeAdapter:
    def __init__(self, result: IpGeolocationReadResult) -> None:
        self._result = result

    def read_records(self) -> IpGeolocationReadResult:
        return self._result


class _ChunkedFakeAdapter:
    def __init__(self, chunks: list[IpGeolocationReadResult]) -> None:
        self._chunks = chunks

    def read_records(self) -> IpGeolocationReadResult:
        return self._chunks[-1]

    def iter_read_results(self, chunk_size: int = 50_000):
        _ = chunk_size
        for chunk in self._chunks:
            yield chunk


class _FailingAdapter:
    def read_records(self) -> IpGeolocationReadResult:
        raise RuntimeError("parse failed")


class _FakeStat:
    def __init__(self, inode: int, mtime_ns: int) -> None:
        self.st_ino = inode
        self.st_mtime_ns = mtime_ns


def test_refresher_skips_publish_when_fingerprint_unchanged() -> None:
    """Second run with same fingerprint should not trigger publish."""
    published: list[tuple[IpGeolocationReadResult, dict[str, object]]] = []

    fingerprints = [
        _FakeStat(10, 1000),
        _FakeStat(10, 1000),
    ]

    def _stat_func(_path: object) -> _FakeStat:
        return fingerprints.pop(0)

    refresher = IpGeolocationDataRefresher(
        publish_snapshot=lambda result, metadata: published.append((result, metadata)),
        adapter=_FakeAdapter(IpGeolocationReadResult(records=[], total_lines=0, malformed_lines=0)),
        stat_func=_stat_func,
        sleep_func=lambda _seconds: None,
    )

    refresher.run_once()
    refresher.run_once()

    assert len(published) == 1
    assert refresher.refresh_attempt_count == 1


def test_refresher_publishes_when_fingerprint_changes() -> None:
    """Fingerprint change should trigger refresh publish path."""
    published: list[tuple[IpGeolocationReadResult, dict[str, object]]] = []

    fingerprints = [
        _FakeStat(10, 1000),
        _FakeStat(11, 2000),
        _FakeStat(11, 2000),
    ]

    def _stat_func(_path: object) -> _FakeStat:
        return fingerprints.pop(0)

    refresher = IpGeolocationDataRefresher(
        publish_snapshot=lambda result, metadata: published.append((result, metadata)),
        adapter=_FakeAdapter(IpGeolocationReadResult(records=[], total_lines=5, malformed_lines=1)),
        stat_func=_stat_func,
        sleep_func=lambda _seconds: None,
    )

    refresher.run_once()
    refresher.run_once()

    assert len(published) == 2
    assert refresher.refresh_attempt_count == 2
    assert refresher.refresh_success_count == 2


def test_refresher_failure_does_not_crash_and_tracks_error() -> None:
    """Adapter failure should keep flow alive and expose refresh error metadata."""
    published: list[tuple[IpGeolocationReadResult, dict[str, object]]] = []

    refresher = IpGeolocationDataRefresher(
        publish_snapshot=lambda result, metadata: published.append((result, metadata)),
        adapter=_FailingAdapter(),
        stat_func=lambda _path: _FakeStat(10, 1000),
        sleep_func=lambda _seconds: None,
    )

    refresher.run_once()

    assert published == []
    assert refresher.refresh_attempt_count == 1
    assert refresher.refresh_failure_count == 1
    assert refresher.last_refresh_error == "parse failed"


def test_refresher_verbose_logs_only_when_refresh_triggered(monkeypatch, caplog) -> None:
    """Verbose mode should log only when a source change triggers refresh/update."""
    published: list[tuple[IpGeolocationReadResult, dict[str, object]]] = []
    monkeypatch.setenv("BGPX_VERBOSE", "1")

    fingerprints = [
        _FakeStat(10, 1000),
        _FakeStat(10, 1000),
    ]

    def _stat_func(_path: object) -> _FakeStat:
        return fingerprints.pop(0)

    refresher = IpGeolocationDataRefresher(
        publish_snapshot=lambda result, metadata: published.append((result, metadata)),
        adapter=_FakeAdapter(IpGeolocationReadResult(records=[], total_lines=3, malformed_lines=0)),
        stat_func=_stat_func,
        sleep_func=lambda _seconds: None,
    )

    with caplog.at_level(logging.INFO):
        refresher.run_once()
        refresher.run_once()

    assert len(published) == 1
    messages = [record.getMessage() for record in caplog.records]
    assert any("source change detected" in message for message in messages)
    assert any("snapshot refresh succeeded" in message for message in messages)
    assert len(messages) == 2


def test_refresher_no_verbose_logs_when_verbose_disabled(monkeypatch, caplog) -> None:
    """Refresh should not emit verbose logs when verbose mode is disabled."""
    published: list[tuple[IpGeolocationReadResult, dict[str, object]]] = []
    monkeypatch.setenv("BGPX_VERBOSE", "0")

    refresher = IpGeolocationDataRefresher(
        publish_snapshot=lambda result, metadata: published.append((result, metadata)),
        adapter=_FakeAdapter(IpGeolocationReadResult(records=[], total_lines=2, malformed_lines=0)),
        stat_func=lambda _path: _FakeStat(99, 1234),
        sleep_func=lambda _seconds: None,
    )

    with caplog.at_level(logging.INFO):
        refresher.run_once()

    assert len(published) == 1
    assert caplog.records == []


def test_refresher_progressively_publishes_chunked_results() -> None:
    """Chunk-capable adapter should publish progressively during refresh."""
    published: list[tuple[IpGeolocationReadResult, dict[str, object]]] = []

    chunks = [
        IpGeolocationReadResult(records=[], total_lines=2, malformed_lines=0),
        IpGeolocationReadResult(records=[], total_lines=4, malformed_lines=1),
    ]

    refresher = IpGeolocationDataRefresher(
        publish_snapshot=lambda result, metadata: published.append((result, metadata)),
        adapter=_ChunkedFakeAdapter(chunks),
        stat_func=lambda _path: _FakeStat(10, 1000),
        sleep_func=lambda _seconds: None,
        publish_chunk_size=2,
    )

    refresher.run_once()

    assert len(published) == 2
    assert published[0][0].total_lines == 2
    assert published[1][0].total_lines == 4
    assert published[1][1]["malformed_lines"] == 1
    assert refresher.refresh_attempt_count == 1
    assert refresher.refresh_success_count == 1
