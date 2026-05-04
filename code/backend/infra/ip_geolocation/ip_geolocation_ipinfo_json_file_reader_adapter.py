"""Infra adapter for reading and parsing IPinfo geolocation NDJSON source file."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

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
        total_lines = 0

        def _iter_lines() -> Iterator[str]:
            nonlocal total_lines
            with DATASET_PATH.open("r", encoding="utf-8") as file_handle:
                for raw_line in file_handle:
                    total_lines += 1
                    yield raw_line

        parsed = parse_ipinfo_ndjson_lines(_iter_lines())
        return IpGeolocationReadResult(
            records=parsed.records,
            total_lines=total_lines,
            malformed_lines=parsed.malformed_count,
        )

    def iter_read_results(self, chunk_size: int = 50_000) -> Iterator[IpGeolocationReadResult]:
        """Stream-read NDJSON file and yield cumulative parse snapshots per chunk."""
        if chunk_size <= 0:
            chunk_size = 1

        total_lines = 0
        malformed_lines = 0
        cumulative_records: list[IpGeolocationRecordModel] = []
        buffer: list[str] = []

        def _flush() -> IpGeolocationReadResult:
            nonlocal malformed_lines
            parsed = parse_ipinfo_ndjson_lines(buffer)
            cumulative_records.extend(parsed.records)
            malformed_lines += parsed.malformed_count
            buffer.clear()
            return IpGeolocationReadResult(
                records=list(cumulative_records),
                total_lines=total_lines,
                malformed_lines=malformed_lines,
            )

        with DATASET_PATH.open("r", encoding="utf-8") as file_handle:
            for raw_line in file_handle:
                total_lines += 1
                buffer.append(raw_line)
                if len(buffer) >= chunk_size:
                    yield _flush()

        if buffer:
            yield _flush()


__all__ = [
    "DATASET_PATH",
    "IpGeolocationIpinfoJsonFileReaderAdapter",
    "IpGeolocationReadResult",
]
