"""Parser utilities for normalizing icmplib ping outcomes."""

from __future__ import annotations

from models.ping import PingResultModel


def parse_ping_result(
    *,
    is_alive: bool,
    ping_time_ms: float | None,
    ttl: int | None,
    ttl_expired: bool,
) -> PingResultModel:
    """Map ping outcome primitives to the shared ping result contract."""
    if ttl_expired:
        return PingResultModel(
            result="success",
            ping_time_ms=ping_time_ms,
            ttl=ttl,
            message="ttl expired",
        )

    if is_alive and ping_time_ms is not None:
        return PingResultModel(
            result="success",
            ping_time_ms=ping_time_ms,
            ttl=ttl,
            message="ping success",
        )

    return PingResultModel(
        result="success",
        ping_time_ms=None,
        ttl=ttl,
        message="ping timeout",
    )
