"""Traceroute app orchestration for higher-layer consumption."""

from __future__ import annotations

from infra.traceroute import TracerouteAdapter
from models.traceroute import TracerouteResultModel


def run_traceroute(
    host: str,
) -> TracerouteResultModel:
    """Run traceroute for a target host via infra adapter and return shared contract."""
    adapter = TracerouteAdapter()
    return adapter.run_traceroute(host)
