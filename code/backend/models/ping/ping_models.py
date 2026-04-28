"""Shared models for ping feature contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class PingResultModel:
    """Normalized ping result contract returned by upper layers."""

    result: Literal["success", "failure"]
    ping_time_ms: float | None
    ttl: int | None
    message: str
