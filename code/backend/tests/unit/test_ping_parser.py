"""Unit tests for ping parser contract mapping."""

from __future__ import annotations

from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from infra.ping.ping_parser import parse_ping_result


def test_parse_ping_result_success_branch() -> None:
    """Parser should map a successful ping outcome to success payload."""
    result = parse_ping_result(
        is_alive=True,
        ping_time_ms=14,
        ttl=57,
        ttl_expired=False,
    )

    assert result.result == "success"
    assert result.ping_time_ms == 14
    assert result.ttl == 57
    assert result.message == "ping success"


def test_parse_ping_result_ttl_expired_branch() -> None:
    """Parser should map ttl-expired outcomes to success payload."""
    result = parse_ping_result(
        is_alive=False,
        ping_time_ms=None,
        ttl=None,
        ttl_expired=True,
    )

    assert result.result == "success"
    assert result.ping_time_ms is None
    assert result.ttl is None
    assert result.message == "ttl expired"


def test_parse_ping_result_timeout_branch() -> None:
    """Parser should map non-success/non-ttl-expired outcomes to timeout success."""
    result = parse_ping_result(
        is_alive=False,
        ping_time_ms=None,
        ttl=64,
        ttl_expired=False,
    )

    assert result.result == "success"
    assert result.ping_time_ms is None
    assert result.ttl == 64
    assert result.message == "ping timeout"
