"""Unit tests for traceroute parser contract mapping."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest


BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from infra.traceroute.traceroute_parser import parse_traceroute_result


class _FakeHop:
    def __init__(
        self,
        *,
        distance: int,
        address: str,
        rtts: list[float],
        packets_sent: int,
    ) -> None:
        self.distance = distance
        self.address = address
        self.rtts = rtts
        self.packets_sent = packets_sent
        self.packets_received = len(rtts)
        self.packet_loss = round(1 - (self.packets_received / packets_sent), 2)
        self.min_rtt = min(rtts) if rtts else 0.0
        self.avg_rtt = (sum(rtts) / len(rtts)) if rtts else 0.0
        self.max_rtt = max(rtts) if rtts else 0.0


def test_parse_traceroute_result_success_branch() -> None:
    """Parser should map successful hops to success payload."""
    result = parse_traceroute_result(
        hops=[_FakeHop(distance=1, address="192.168.1.1", rtts=[1.2, 1.4], packets_sent=2)],
        had_error=False,
        reached_target=True,
    )

    assert result.result == "success"
    assert result.message == "traceroute completed: success"
    assert len(result.hops) == 1
    assert result.hops[0].distance == 1
    assert result.hops[0].address == "192.168.1.1"
    assert result.hops[0].avg_rtt_ms == pytest.approx(1.3)


def test_parse_traceroute_result_timeout_branch() -> None:
    """Parser should map empty hop responses to timeout completion outcome."""
    result = parse_traceroute_result(hops=[], had_error=False)

    assert result.result == "success"
    assert result.hops == []
    assert result.message == "traceroute completed: timeout"


def test_parse_traceroute_result_error_branch() -> None:
    """Parser should map adapter error states to failure payload."""
    result = parse_traceroute_result(hops=[], had_error=True)

    assert result.result == "failure"
    assert result.hops == []
    assert result.message == "traceroute failed"


def test_parse_traceroute_result_error_branch_uses_custom_message() -> None:
    """Parser should preserve adapter-provided error messages when present."""
    result = parse_traceroute_result(
        hops=[],
        had_error=True,
        error_message="traceroute failed: insufficient permissions",
    )

    assert result.result == "failure"
    assert result.hops == []
    assert result.message == "traceroute failed: insufficient permissions"


def test_parse_traceroute_result_not_reached_branch() -> None:
    """Parser should map non-empty but unreached route to completion outcome."""
    result = parse_traceroute_result(
        hops=[_FakeHop(distance=1, address="10.0.0.1", rtts=[1.0], packets_sent=1)],
        had_error=False,
        reached_target=False,
    )

    assert result.result == "success"
    assert len(result.hops) == 1
    assert result.message == "traceroute completed: destination not reached within max hops"


def test_parse_traceroute_result_not_reached_uses_custom_message() -> None:
    """Parser should preserve custom completion message when destination is not reached."""
    result = parse_traceroute_result(
        hops=[_FakeHop(distance=1, address="10.0.0.1", rtts=[1.0], packets_sent=1)],
        had_error=False,
        reached_target=False,
        error_message="traceroute completed: routing loop detected",
    )

    assert result.result == "success"
    assert len(result.hops) == 1
    assert result.message == "traceroute completed: routing loop detected"
