"""Traceroute app orchestration for higher-layer consumption."""

from __future__ import annotations

import ipaddress

from apps.ip_geolocation import get_ip_geolocation_service
from infra.traceroute import TracerouteAdapter
from models.traceroute import TracerouteHopModel, TracerouteResultModel


def run_traceroute(
    host: str,
) -> TracerouteResultModel:
    """Run traceroute and enrich hop rows with geolocation details from IP lookup service."""
    adapter = TracerouteAdapter()
    result = adapter.run_traceroute(host)

    if result.result != "success" or not result.hops:
        return result

    enriched_hops = []
    for hop in result.hops:
        country, country_code, asn, as_name = _resolve_hop_geo_info(hop.address)
        enriched_hops.append(
            TracerouteHopModel(
                distance=hop.distance,
                address=hop.address,
                rtts_ms=hop.rtts_ms,
                avg_rtt_ms=hop.avg_rtt_ms,
                min_rtt_ms=hop.min_rtt_ms,
                max_rtt_ms=hop.max_rtt_ms,
                packets_sent=hop.packets_sent,
                packets_received=hop.packets_received,
                packet_loss=hop.packet_loss,
                country=country,
                country_code=country_code,
                asn=asn,
                as_name=as_name,
            )
        )

    return TracerouteResultModel(
        result=result.result,
        hops=enriched_hops,
        message=result.message,
    )


def _resolve_hop_geo_info(address: str) -> tuple[str | None, str | None, str | None, str | None]:
    """Return country/ASN details for a hop address if available in geolocation DB."""
    candidate = address.strip()
    if not candidate or candidate == "*":
        return None, None, None, None

    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return None, None, None, None

    lookup = get_ip_geolocation_service().lookup_ip_geolocation(candidate)
    if lookup.status != "success":
        return None, None, None, None

    return (
        getattr(lookup.data, "country", None),
        getattr(lookup.data, "country_code", None),
        getattr(lookup.data, "asn", None),
        getattr(lookup.data, "as_name", None),
    )
