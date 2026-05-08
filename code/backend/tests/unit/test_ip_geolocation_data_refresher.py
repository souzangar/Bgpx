"""Unit tests for IP geolocation data refresher behavior."""

from __future__ import annotations

import logging
from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from infra.ip_geolocation import IpGeolocationReadResult
from models.ip_geolocation import IpGeolocationRecordModel
from services.ip_geolocation.ip_geolocation_data_refresher import IpGeolocationDataRefresher


class _FakeAdapter:
    def __init__(self, result: IpGeolocationReadResult) -> None:
        self._result = result
        self.read_count = 0

    def read_records(self) -> IpGeolocationReadResult:
        self.read_count += 1
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


def _localhost_override_record() -> IpGeolocationRecordModel:
    return IpGeolocationRecordModel(
        network="127.0.0.0/30",
        country="Your PC",
        country_code="YP",
        continent="Planet Earth",
        continent_code="PE",
        asn="AS_197",
        as_name="BGPX Team",
        as_domain="bgpx.net",
    )


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


def test_refresher_info_logs_show_refresh_events(monkeypatch, caplog) -> None:
    """INFO level should show state-change refresh events."""
    published: list[tuple[IpGeolocationReadResult, dict[str, object]]] = []

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

    with caplog.at_level(logging.INFO, logger="bgpx.tasks.ip_geo.refresher"):
        refresher.run_once()
        refresher.run_once()

    assert len(published) == 1
    messages = [record.getMessage() for record in caplog.records]
    assert any("source change detected" in message for message in messages)
    assert all("refresh chunk published" not in message for message in messages)
    assert any("snapshot refresh succeeded" in message for message in messages)
    assert any("localhost override first-record validation failed" in message for message in messages)
    assert len(messages) == 3


def test_refresher_debug_logs_each_chunk_publish(caplog) -> None:
    """DEBUG level should emit one publish log per chunk."""
    chunks = [
        IpGeolocationReadResult(records=[], total_lines=2, malformed_lines=0),
        IpGeolocationReadResult(records=[], total_lines=4, malformed_lines=1),
    ]

    refresher = IpGeolocationDataRefresher(
        publish_snapshot=lambda _result, _metadata: None,
        adapter=_ChunkedFakeAdapter(chunks),
        stat_func=lambda _path: _FakeStat(10, 1000),
        sleep_func=lambda _seconds: None,
        publish_chunk_size=2,
    )

    with caplog.at_level(logging.DEBUG, logger="bgpx.tasks.ip_geo.refresher"):
        refresher.run_once()

    chunk_messages = [record.getMessage() for record in caplog.records if "refresh chunk published" in record.getMessage()]
    assert len(chunk_messages) == 2
    assert "chunk=1" in chunk_messages[0]
    assert "is_final_chunk=False" in chunk_messages[0]
    assert "chunk=2" in chunk_messages[1]
    assert "is_final_chunk=True" in chunk_messages[1]


def test_refresher_warning_level_suppresses_info_and_debug_logs(caplog) -> None:
    """WARNING level should suppress routine info/debug refresher logs."""
    published: list[tuple[IpGeolocationReadResult, dict[str, object]]] = []

    refresher = IpGeolocationDataRefresher(
        publish_snapshot=lambda result, metadata: published.append((result, metadata)),
        adapter=_FakeAdapter(IpGeolocationReadResult(records=[], total_lines=2, malformed_lines=0)),
        stat_func=lambda _path: _FakeStat(99, 1234),
        sleep_func=lambda _seconds: None,
    )

    with caplog.at_level(logging.WARNING, logger="bgpx.tasks.ip_geo.refresher"):
        refresher.run_once()

    assert len(published) == 1
    messages = [record.getMessage() for record in caplog.records]
    assert all("source change detected" not in message for message in messages)
    assert all("snapshot refresh succeeded" not in message for message in messages)
    assert any("localhost override first-record validation failed" in message for message in messages)


def test_refresher_debug_logs_include_unchanged_cycle(caplog) -> None:
    """DEBUG level should include per-cycle unchanged diagnostics."""

    fingerprints = [
        _FakeStat(10, 1000),
        _FakeStat(10, 1000),
    ]

    def _stat_func(_path: object) -> _FakeStat:
        return fingerprints.pop(0)

    refresher = IpGeolocationDataRefresher(
        publish_snapshot=lambda _result, _metadata: None,
        adapter=_FakeAdapter(IpGeolocationReadResult(records=[], total_lines=1, malformed_lines=0)),
        stat_func=_stat_func,
        sleep_func=lambda _seconds: None,
    )

    with caplog.at_level(logging.DEBUG, logger="bgpx.tasks.ip_geo.refresher"):
        refresher.run_once()

    with caplog.at_level(logging.DEBUG, logger="bgpx.tasks.ip_geo.refresher"):
        refresher.run_once()

    messages = [record.getMessage() for record in caplog.records]
    assert any("poll tick started" in message for message in messages)
    assert any("poll tick unchanged" in message for message in messages)


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
    assert published[0][1]["is_final_chunk"] is False
    assert published[1][1]["is_final_chunk"] is True
    assert published[1][1]["malformed_lines"] == 1
    assert refresher.refresh_attempt_count == 1
    assert refresher.refresh_success_count == 1


def test_refresher_skips_publish_when_fingerprint_changes_but_content_equivalent() -> None:
    """Changed fingerprint with equivalent content should skip publish and mark success."""
    published: list[tuple[IpGeolocationReadResult, dict[str, object]]] = []

    fingerprints = [
        _FakeStat(10, 1000),
        _FakeStat(11, 2000),
        _FakeStat(11, 2000),
    ]

    def _stat_func(_path: object) -> _FakeStat:
        return fingerprints.pop(0)

    adapter = _FakeAdapter(IpGeolocationReadResult(records=[], total_lines=5, malformed_lines=0))
    refresher = IpGeolocationDataRefresher(
        publish_snapshot=lambda result, metadata: published.append((result, metadata)),
        is_snapshot_equivalent=lambda _candidate: True,
        adapter=adapter,
        stat_func=_stat_func,
        sleep_func=lambda _seconds: None,
    )

    refresher.run_once()
    refresher.run_once()

    assert len(published) == 1
    assert refresher.refresh_attempt_count == 2
    assert refresher.refresh_success_count == 2
    assert adapter.read_count == 2


def test_refresher_applies_delta_when_available_and_content_changed() -> None:
    """Changed fingerprint should prefer delta apply path when callback accepts it."""
    published: list[tuple[IpGeolocationReadResult, dict[str, object]]] = []
    delta_calls: list[tuple[IpGeolocationReadResult, dict[str, object]]] = []

    fingerprints = [
        _FakeStat(10, 1000),
        _FakeStat(11, 2000),
        _FakeStat(11, 2000),
    ]

    def _stat_func(_path: object) -> _FakeStat:
        return fingerprints.pop(0)

    adapter = _FakeAdapter(IpGeolocationReadResult(records=[], total_lines=5, malformed_lines=0))
    refresher = IpGeolocationDataRefresher(
        publish_snapshot=lambda result, metadata: published.append((result, metadata)),
        is_snapshot_equivalent=lambda _candidate: False,
        apply_snapshot_delta=lambda result, metadata: delta_calls.append((result, metadata)) or True,
        adapter=adapter,
        stat_func=_stat_func,
        sleep_func=lambda _seconds: None,
    )

    refresher.run_once()
    refresher.run_once()

    assert len(published) == 1
    assert len(delta_calls) == 1
    assert refresher.refresh_attempt_count == 2
    assert refresher.refresh_success_count == 2
    assert adapter.read_count == 2


def test_refresher_falls_back_to_full_publish_when_delta_rejected() -> None:
    """When delta callback returns False, refresher should publish full snapshot."""
    published: list[tuple[IpGeolocationReadResult, dict[str, object]]] = []

    fingerprints = [
        _FakeStat(10, 1000),
        _FakeStat(11, 2000),
        _FakeStat(11, 2000),
    ]

    def _stat_func(_path: object) -> _FakeStat:
        return fingerprints.pop(0)

    adapter = _FakeAdapter(IpGeolocationReadResult(records=[], total_lines=5, malformed_lines=0))
    refresher = IpGeolocationDataRefresher(
        publish_snapshot=lambda result, metadata: published.append((result, metadata)),
        is_snapshot_equivalent=lambda _candidate: False,
        apply_snapshot_delta=lambda _result, _metadata: False,
        adapter=adapter,
        stat_func=_stat_func,
        sleep_func=lambda _seconds: None,
    )

    refresher.run_once()
    refresher.run_once()

    assert len(published) == 2
    assert refresher.refresh_attempt_count == 2
    assert refresher.refresh_success_count == 2


def test_refresher_debug_logs_localhost_override_present(caplog) -> None:
    """Refresher should log debug when localhost override is present as first record."""
    refresher = IpGeolocationDataRefresher(
        publish_snapshot=lambda _result, _metadata: None,
        adapter=_FakeAdapter(IpGeolocationReadResult(records=[_localhost_override_record()], total_lines=1, malformed_lines=0)),
        stat_func=lambda _path: _FakeStat(10, 1000),
        sleep_func=lambda _seconds: None,
    )

    with caplog.at_level(logging.DEBUG, logger="bgpx.tasks.ip_geo.refresher"):
        refresher.run_once()

    messages = [record.getMessage() for record in caplog.records]
    assert any("localhost override validation passed" in message for message in messages)


def test_refresher_warns_when_localhost_override_missing(caplog) -> None:
    """Refresher should warn when first record is not the expected localhost override."""
    non_override_record = IpGeolocationRecordModel(
        network="1.1.1.0/24",
        country="AU",
        country_code="AU",
        continent="Oceania",
        continent_code="OC",
        asn="AS13335",
        as_name="Cloudflare",
        as_domain="cloudflare.com",
    )
    refresher = IpGeolocationDataRefresher(
        publish_snapshot=lambda _result, _metadata: None,
        adapter=_FakeAdapter(IpGeolocationReadResult(records=[non_override_record], total_lines=1, malformed_lines=0)),
        stat_func=lambda _path: _FakeStat(10, 1000),
        sleep_func=lambda _seconds: None,
    )

    with caplog.at_level(logging.WARNING, logger="bgpx.tasks.ip_geo.refresher"):
        refresher.run_once()

    messages = [record.getMessage() for record in caplog.records]
    assert any("localhost override validation failed" in message for message in messages)
