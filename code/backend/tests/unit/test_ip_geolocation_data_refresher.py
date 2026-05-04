"""Unit tests for IP geolocation data refresher behavior."""

from __future__ import annotations

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
