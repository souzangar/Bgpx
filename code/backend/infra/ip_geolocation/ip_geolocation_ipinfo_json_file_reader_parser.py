"""Parser utilities for IPinfo NDJSON geolocation records."""

from __future__ import annotations

import ipaddress
import json
from dataclasses import dataclass
from typing import Iterable

from models.ip_geolocation import IpGeolocationRecordModel


@dataclass(frozen=True)
class IpGeolocationParseOutput:
    """Parser output containing normalized records and malformed-line count."""

    records: list[IpGeolocationRecordModel]
    malformed_count: int


def parse_ipinfo_ndjson_lines(lines: Iterable[str]) -> IpGeolocationParseOutput:
    """Parse NDJSON lines into normalized geolocation records."""
    records: list[IpGeolocationRecordModel] = []
    malformed_count = 0

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        try:
            payload = json.loads(line)
            network = _normalize_network(str(payload["network"]))
            record = IpGeolocationRecordModel(
                network=network,
                country=str(payload["country"]),
                country_code=str(payload["country_code"]),
                continent=str(payload["continent"]),
                continent_code=str(payload["continent_code"]),
                asn=_optional_text(payload.get("asn")),
                as_name=_optional_text(payload.get("as_name")),
                as_domain=_optional_text(payload.get("as_domain")),
            )
            records.append(record)
        except Exception:
            malformed_count += 1

    return IpGeolocationParseOutput(records=records, malformed_count=malformed_count)


def _normalize_network(value: str) -> str:
    """Normalize network field to canonical CIDR representation."""
    network_value = value.strip()
    if not network_value:
        raise ValueError("network is empty")

    if "/" in network_value:
        return str(ipaddress.ip_network(network_value, strict=False))

    host_ip = ipaddress.ip_address(network_value)
    suffix = "32" if host_ip.version == 4 else "128"
    return str(ipaddress.ip_network(f"{host_ip}/{suffix}", strict=False))


def _optional_text(value: object) -> str | None:
    """Normalize optional text fields while keeping null as null."""
    if value is None:
        return None

    text = str(value).strip()
    return text or None


__all__ = ["IpGeolocationParseOutput", "parse_ipinfo_ndjson_lines"]
