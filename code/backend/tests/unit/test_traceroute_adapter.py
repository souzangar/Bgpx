"""Unit tests for traceroute adapter behavior and error handling."""

from __future__ import annotations

from pathlib import Path
import sys

from icmplib import Hop
from icmplib.exceptions import NameLookupError
from icmplib.exceptions import TimeExceeded
import pytest


BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from infra.traceroute.traceroute_adapter import TracerouteAdapter


class _FakeHop:
    def __init__(self) -> None:
        self.distance = 1
        self.address = "10.0.0.1"
        self.rtts = [2.0, 4.0]
        self.packets_sent = 2
        self.packets_received = 2
        self.packet_loss = 0.0
        self.min_rtt = 2.0
        self.avg_rtt = 3.0
        self.max_rtt = 4.0


def test_run_traceroute_returns_success_payload(monkeypatch) -> None:
    """Adapter should normalize successful traceroute responses."""

    def _fake_execute_traceroute(
        host: str,
        *,
        count: int,
        timeout: float,
        max_hops: int,
        fast: bool,
    ):
        assert host == "example.com"
        assert count == 1
        assert timeout == 1
        assert max_hops == 30
        assert fast is True
        return [Hop(address="10.0.0.1", packets_sent=2, rtts=[2.0, 4.0], distance=1)], True

    monkeypatch.setattr(
        "infra.traceroute.traceroute_adapter.TracerouteAdapter._execute_traceroute",
        staticmethod(_fake_execute_traceroute),
    )

    result = TracerouteAdapter().run_traceroute("example.com")

    assert result.result == "success"
    assert result.message == "traceroute completed: success"
    assert len(result.hops) == 1
    assert result.hops[0].address == "10.0.0.1"
    assert result.hops[0].avg_rtt_ms == pytest.approx(3.0)


def test_run_traceroute_maps_icmplib_error_to_failure(monkeypatch) -> None:
    """Adapter should map icmplib exceptions to a failure result."""

    def _fake_execute_traceroute(host: str, *, count: int, timeout: float, max_hops: int, fast: bool):
        raise NameLookupError(host)

    monkeypatch.setattr(
        "infra.traceroute.traceroute_adapter.TracerouteAdapter._execute_traceroute",
        staticmethod(_fake_execute_traceroute),
    )

    result = TracerouteAdapter().run_traceroute("invalid-host")

    assert result.result == "failure"
    assert result.hops == []
    assert result.message == "traceroute failed: name resolution error"


def test_run_traceroute_maps_unexpected_error_to_failure(monkeypatch) -> None:
    """Adapter should gracefully handle non-icmplib unexpected exceptions."""

    def _fake_execute_traceroute(host: str, *, count: int, timeout: float, max_hops: int, fast: bool):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "infra.traceroute.traceroute_adapter.TracerouteAdapter._execute_traceroute",
        staticmethod(_fake_execute_traceroute),
    )

    result = TracerouteAdapter().run_traceroute("example.com")

    assert result.result == "failure"
    assert result.hops == []
    assert result.message == "traceroute failed: boom"


def test_run_traceroute_loop_detection_maps_to_failure(monkeypatch) -> None:
    """Adapter should classify unreached cyclic hops as completed route outcome."""

    loop_hops = [
        Hop(address="10.0.34.1", packets_sent=1, rtts=[1.0], distance=1),
        Hop(address="10.0.34.78", packets_sent=1, rtts=[1.0], distance=2),
        Hop(address="10.0.34.1", packets_sent=1, rtts=[1.0], distance=3),
        Hop(address="10.0.34.78", packets_sent=1, rtts=[1.0], distance=4),
        Hop(address="10.0.34.1", packets_sent=1, rtts=[1.0], distance=5),
        Hop(address="10.0.34.78", packets_sent=1, rtts=[1.0], distance=6),
    ]

    def _fake_execute_traceroute(host: str, *, count: int, timeout: float, max_hops: int, fast: bool):
        return loop_hops, False

    monkeypatch.setattr(
        "infra.traceroute.traceroute_adapter.TracerouteAdapter._execute_traceroute",
        staticmethod(_fake_execute_traceroute),
    )

    result = TracerouteAdapter().run_traceroute("example.com")

    assert result.result == "success"
    assert result.message == "traceroute completed: routing loop detected"
    assert len(result.hops) == 6


def test_execute_traceroute_includes_timeout_hops_in_sequence(monkeypatch: pytest.MonkeyPatch) -> None:
    """Adapter should include explicit '*' hops for middle TTLs that fully timeout."""

    class _FakeRequest:
        def __init__(self, destination: str, id: int, sequence: int, ttl: int) -> None:
            self.destination = destination
            self.id = id
            self.sequence = sequence
            self.ttl = ttl
            self.time = float(ttl)

    class _FakeReply:
        def __init__(self, source: str, ttl: int, *, reached: bool) -> None:
            self.source = source
            self.time = float(ttl) + 0.001
            self.reached = reached

        def raise_for_status(self) -> None:
            if not self.reached:
                reply_meta = type("ReplyMeta", (), {"code": 0})()
                raise TimeExceeded(reply_meta)
            return None

    class _FakeSocket:
        def __init__(self, privileged: bool) -> None:
            self.privileged = privileged

        def __enter__(self) -> "_FakeSocket":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def send(self, request: _FakeRequest) -> None:
            request.time = float(request.ttl)

        def receive(self, request: _FakeRequest, timeout: int):
            # TTL=3 simulates a full timeout (no reply at all).
            if request.ttl == 1:
                return _FakeReply("10.0.0.1", ttl=1, reached=False)
            if request.ttl == 2:
                return _FakeReply("10.0.0.2", ttl=2, reached=False)
            if request.ttl == 3:
                return None
            if request.ttl == 4:
                return _FakeReply("10.0.0.4", ttl=4, reached=True)
            return None

    monkeypatch.setattr("infra.traceroute.traceroute_adapter.is_hostname", lambda host: False)
    monkeypatch.setattr("infra.traceroute.traceroute_adapter.is_ipv6_address", lambda host: False)
    monkeypatch.setattr("infra.traceroute.traceroute_adapter.ICMPRequest", _FakeRequest)
    monkeypatch.setattr("infra.traceroute.traceroute_adapter.ICMPv4Socket", _FakeSocket)
    monkeypatch.setattr("infra.traceroute.traceroute_adapter.unique_identifier", lambda: 1)

    hops, reached_target = TracerouteAdapter._execute_traceroute(
        "8.8.8.8",
        count=1,
        timeout=1,
        max_hops=4,
        fast=True,
    )

    assert reached_target is True
    assert [hop.distance for hop in hops] == [1, 2, 3, 4]
    assert [str(hop.address) for hop in hops] == ["10.0.0.1", "10.0.0.2", "*", "10.0.0.4"]
    assert hops[2].packets_sent == 1
    assert hops[2].rtts == []
