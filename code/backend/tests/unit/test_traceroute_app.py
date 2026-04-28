"""Unit tests for traceroute app orchestration."""

from __future__ import annotations

from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from apps.traceroute import run_traceroute
from models.traceroute import TracerouteResultModel


def test_run_traceroute_calls_adapter_with_expected_args(monkeypatch) -> None:
    """App should orchestrate adapter call and return adapter output unchanged."""

    expected = TracerouteResultModel(result="success", hops=[], message="traceroute success")

    captured: dict[str, object] = {}

    def _fake_run_traceroute(self, host: str):
        captured["host"] = host
        return expected

    monkeypatch.setattr(
        "infra.traceroute.traceroute_adapter.TracerouteAdapter.run_traceroute",
        _fake_run_traceroute,
    )

    result = run_traceroute("example.com")

    assert result is expected
    assert captured == {
        "host": "example.com",
    }
