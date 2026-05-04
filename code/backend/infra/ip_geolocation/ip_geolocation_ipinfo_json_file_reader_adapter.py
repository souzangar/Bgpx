"""Infra adapter for reading and parsing IPinfo geolocation NDJSON source file."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from models.ip_geolocation import IpGeolocationRecordModel

from .ip_geolocation_ipinfo_json_file_reader_parser import (
    parse_ipinfo_ndjson_lines,
)


DATASET_PATH = Path("code/backend/data/ip_geolocation/ipinfo-geo.json")


@dataclass(frozen=True)
class IpGeolocationReadResult:
    """Adapter output for downstream refresher/service ingestion."""

    records: list[IpGeolocationRecordModel]
    total_lines: int
    malformed_lines: int


class IpGeolocationIpinfoJsonFileReaderAdapter:
    """Read provider dataset from fixed path and return normalized parser output."""

    def read_records(self) -> IpGeolocationReadResult:
        """Load NDJSON dataset and return normalized records and line metrics."""
        lines = DATASET_PATH.read_text(encoding="utf-8").splitlines()
        parsed = parse_ipinfo_ndjson_lines(lines)
        return IpGeolocationReadResult(
            records=parsed.records,
            total_lines=len(lines),
            malformed_lines=parsed.malformed_count,
        )


__all__ = [
    "DATASET_PATH",
    "IpGeolocationIpinfoJsonFileReaderAdapter",
    "IpGeolocationReadResult",
]
