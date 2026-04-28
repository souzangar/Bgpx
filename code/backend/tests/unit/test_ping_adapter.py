"""Unit tests for ping adapter behavior and ttl-expired classification."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest
from icmplib.exceptions import TimeExceeded


BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from infra.ping.ping_adapter import PingAdapter


class _FakeRequest:
    def __init__(self, destination: str, id: int, sequence: int) -> None:
        self.destination = destination
        self.id = id
        self.sequence = sequence
        self.time = 1.0


class _FakeReplySuccess:
    def __init__(self, time: float, ttl: int = 57) -> None:
        self.time = time
        self.ttl = ttl

    def raise_for_status(self) -> None:
        return None


class _FakeReplyTTLExpired:
    family = 4
    type = 11
    time = 1.0

    def raise_for_status(self) -> None:
        reply_meta = type("ReplyMeta", (), {"code": 0})()
        raise TimeExceeded(reply_meta)


class _FakeReplyTTLExpiredMetadataOnly:
    family = 4
    type = 11
    time = 1.0

    def raise_for_status(self) -> None:
        msg = "raise_for_status should not be called for TTL-expired replies"
        raise AssertionError(msg)


def test_probe_once_returns_ttl_expired_on_time_exceeded(monkeypatch: pytest.MonkeyPatch) -> None:
    """Adapter should detect ttl-expired when socket reply raises TimeExceeded."""

    class _FakeSocket:
        def __init__(self, source: str | None, privileged: bool) -> None:
            # Intentionally empty: test double only matches real socket signature.
            pass

        def __enter__(self) -> "_FakeSocket":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def send(self, request: _FakeRequest) -> None:
            request.time = 1.0

        def receive(self, request: _FakeRequest, timeout: float) -> _FakeReplyTTLExpired:
            return _FakeReplyTTLExpired()

    monkeypatch.setattr("infra.ping.ping_adapter.is_hostname", lambda host: False)
    monkeypatch.setattr("infra.ping.ping_adapter.is_ipv6_address", lambda host: False)
    monkeypatch.setattr("infra.ping.ping_adapter.ICMPRequest", _FakeRequest)
    monkeypatch.setattr("infra.ping.ping_adapter.ICMPv4Socket", _FakeSocket)

    adapter = PingAdapter()
    is_alive, ping_time_ms, ttl, ttl_expired = adapter._probe_once("8.8.8.8")

    assert is_alive is False
    assert ping_time_ms is None
    assert ttl is None
    assert ttl_expired is True


def test_probe_once_returns_ttl_expired_from_reply_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    """Adapter should detect ttl-expired from ICMP Time Exceeded reply metadata."""

    class _FakeSocket:
        def __init__(self, source: str | None, privileged: bool) -> None:
            # Intentionally empty: test double only matches real socket signature.
            pass

        def __enter__(self) -> "_FakeSocket":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def send(self, request: _FakeRequest) -> None:
            request.time = 1.0

        def receive(self, request: _FakeRequest, timeout: float) -> _FakeReplyTTLExpiredMetadataOnly:
            return _FakeReplyTTLExpiredMetadataOnly()

    monkeypatch.setattr("infra.ping.ping_adapter.is_hostname", lambda host: False)
    monkeypatch.setattr("infra.ping.ping_adapter.is_ipv6_address", lambda host: False)
    monkeypatch.setattr("infra.ping.ping_adapter.ICMPRequest", _FakeRequest)
    monkeypatch.setattr("infra.ping.ping_adapter.ICMPv4Socket", _FakeSocket)

    adapter = PingAdapter()
    is_alive, ping_time_ms, ttl, ttl_expired = adapter._probe_once("8.8.8.8")

    assert is_alive is False
    assert ping_time_ms is None
    assert ttl is None
    assert ttl_expired is True


def test_probe_once_returns_success_when_echo_reply_received(monkeypatch: pytest.MonkeyPatch) -> None:
    """Adapter should return success and RTT when reply status is healthy."""

    class _FakeSocket:
        def __init__(self, source: str | None, privileged: bool) -> None:
            # Intentionally empty: test double only matches real socket signature.
            pass

        def __enter__(self) -> "_FakeSocket":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def send(self, request: _FakeRequest) -> None:
            request.time = 1.0

        def receive(self, request: _FakeRequest, timeout: float) -> _FakeReplySuccess:
            return _FakeReplySuccess(time=1.125)

    monkeypatch.setattr("infra.ping.ping_adapter.is_hostname", lambda host: False)
    monkeypatch.setattr("infra.ping.ping_adapter.is_ipv6_address", lambda host: False)
    monkeypatch.setattr("infra.ping.ping_adapter.ICMPRequest", _FakeRequest)
    monkeypatch.setattr("infra.ping.ping_adapter.ICMPv4Socket", _FakeSocket)

    adapter = PingAdapter()
    is_alive, ping_time_ms, ttl, ttl_expired = adapter._probe_once("1.1.1.1")

    assert is_alive is True
    assert ping_time_ms == pytest.approx(125.0)
    assert ttl == 57
    assert ttl_expired is False


def test_run_ping_maps_ttl_expired_to_expected_message(monkeypatch: pytest.MonkeyPatch) -> None:
    """Top-level adapter output should expose ttl-expired parser message."""
    monkeypatch.setattr(PingAdapter, "_probe_once", lambda self, host: (False, None, None, True))

    result = PingAdapter().run_ping("example.com")

    assert result.result == "success"
    assert result.message == "ttl expired"


def test_run_ping_maps_success_ttl_to_result(monkeypatch: pytest.MonkeyPatch) -> None:
    """Top-level adapter output should expose ttl value on successful ping."""
    monkeypatch.setattr(PingAdapter, "_probe_once", lambda self, host: (True, 12, 61, False))

    result = PingAdapter().run_ping("example.com")

    assert result.result == "success"
    assert result.message == "ping success"
    assert result.ping_time_ms == 12
    assert result.ttl == 61
