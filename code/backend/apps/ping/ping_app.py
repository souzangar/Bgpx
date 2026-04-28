"""Ping app orchestration for higher-layer consumption."""

from __future__ import annotations

from infra.ping import PingAdapter
from models.ping import PingResultModel


def run_ping(host: str) -> PingResultModel:
    """Run ping for a target host via infra adapter and return shared contract."""
    adapter = PingAdapter()
    return adapter.run_ping(host)
