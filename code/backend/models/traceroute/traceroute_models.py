"""Shared models for traceroute feature contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class TracerouteHopModel:
    """Normalized traceroute hop contract returned by upper layers."""

    distance: int
    address: str
    rtts_ms: list[float]
    avg_rtt_ms: float
    min_rtt_ms: float
    max_rtt_ms: float
    packets_sent: int
    packets_received: int
    packet_loss: float


@dataclass(frozen=True)
class TracerouteResultModel:
    """Normalized traceroute result contract returned by upper layers."""

    result: Literal["success", "failure"]
    hops: list[TracerouteHopModel]
    message: str
