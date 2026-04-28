"""Parser utilities for normalizing icmplib traceroute outcomes."""

from __future__ import annotations

from models.traceroute import TracerouteHopModel, TracerouteResultModel


def parse_traceroute_result(
    *,
    hops: list[object],
    had_error: bool,
    reached_target: bool = False,
    error_message: str | None = None,
) -> TracerouteResultModel:
    """Map raw traceroute primitives to the shared traceroute result contract."""
    if had_error:
        message = (error_message or "traceroute failed").strip() or "traceroute failed"
        return TracerouteResultModel(result="failure", hops=[], message=message)

    if not hops:
        return TracerouteResultModel(
            result="success",
            hops=[],
            message="traceroute completed: timeout",
        )

    normalized_hops = [_parse_hop(hop) for hop in hops]

    if not reached_target:
        message = (error_message or "traceroute completed: destination not reached within max hops").strip()
        return TracerouteResultModel(result="success", hops=normalized_hops, message=message)

    return TracerouteResultModel(
        result="success",
        hops=normalized_hops,
        message="traceroute completed: success",
    )


def _parse_hop(hop: object) -> TracerouteHopModel:
    """Normalize a raw icmplib Hop-like object to the shared hop contract."""
    raw_rtts = getattr(hop, "rtts", []) or []
    rtts_ms = [float(rtt) for rtt in raw_rtts]

    min_rtt_ms = float(getattr(hop, "min_rtt", min(rtts_ms) if rtts_ms else 0.0))
    avg_rtt_ms = float(getattr(hop, "avg_rtt", (sum(rtts_ms) / len(rtts_ms)) if rtts_ms else 0.0))
    max_rtt_ms = float(getattr(hop, "max_rtt", max(rtts_ms) if rtts_ms else 0.0))

    packets_sent = int(getattr(hop, "packets_sent", len(rtts_ms)))
    packets_received = int(getattr(hop, "packets_received", len(rtts_ms)))
    packet_loss = float(
        getattr(
            hop,
            "packet_loss",
            (1 - (packets_received / packets_sent)) if packets_sent else 0.0,
        )
    )

    return TracerouteHopModel(
        distance=int(getattr(hop, "distance", 0)),
        address=str(getattr(hop, "address", "*")),
        rtts_ms=rtts_ms,
        avg_rtt_ms=avg_rtt_ms,
        min_rtt_ms=min_rtt_ms,
        max_rtt_ms=max_rtt_ms,
        packets_sent=packets_sent,
        packets_received=packets_received,
        packet_loss=packet_loss,
    )
