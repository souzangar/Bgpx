"""Unit tests for traceroute app orchestration."""

from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace


BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from apps.traceroute import run_traceroute
from models.traceroute import TracerouteHopModel, TracerouteResultModel


def test_run_traceroute_calls_adapter_with_expected_args(monkeypatch) -> None:
    """App should orchestrate adapter call and enrich hop rows with country code."""

    expected = TracerouteResultModel(
        result="success",
        hops=[
            TracerouteHopModel(
                distance=1,
                address="8.8.8.8",
                rtts_ms=[10.0],
                avg_rtt_ms=10.0,
                min_rtt_ms=10.0,
                max_rtt_ms=10.0,
                packets_sent=1,
                packets_received=1,
                packet_loss=0.0,
            ),
            TracerouteHopModel(
                distance=2,
                address="*",
                rtts_ms=[],
                avg_rtt_ms=0.0,
                min_rtt_ms=0.0,
                max_rtt_ms=0.0,
                packets_sent=1,
                packets_received=0,
                packet_loss=1.0,
            ),
        ],
        message="traceroute success",
    )

    captured: dict[str, object] = {}

    def _fake_run_traceroute(self, host: str):
        captured["host"] = host
        return expected

    monkeypatch.setattr(
        "infra.traceroute.traceroute_adapter.TracerouteAdapter.run_traceroute",
        _fake_run_traceroute,
    )

    class _FakeIpGeoService:
        def lookup_ip_geolocation(self, ip: str):
            if ip == "8.8.8.8":
                return SimpleNamespace(status="success", data=SimpleNamespace(country_code="US"))
            return SimpleNamespace(status="success", data=SimpleNamespace(country_code=None))

    monkeypatch.setattr(
        "apps.traceroute.traceroute_app.get_ip_geolocation_service",
        lambda: _FakeIpGeoService(),
    )

    result = run_traceroute("example.com")

    assert result is not expected
    assert captured == {
        "host": "example.com",
    }
    assert result.hops[0].country_code == "US"
    assert result.hops[1].country_code is None
