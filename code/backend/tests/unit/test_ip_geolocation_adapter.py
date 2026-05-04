"""Unit tests for IP geolocation file reader adapter behavior."""

from __future__ import annotations

from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from infra.ip_geolocation.ip_geolocation_ipinfo_json_file_reader_adapter import (  # noqa: E402
    IpGeolocationIpinfoJsonFileReaderAdapter,
)


def test_ip_geolocation_adapter_reads_and_parses_ndjson_file(tmp_path: Path) -> None:
    """Adapter should read file, parse records, and report malformed line counts."""
    data_file = tmp_path / "ipinfo-geo.json"
    data_file.write_text(
        "\n".join(
            [
                '{"network":"1.1.1.0/24","country":"Australia","country_code":"AU","continent":"Oceania","continent_code":"OC","asn":"AS13335","as_name":"Cloudflare, Inc.","as_domain":"cloudflare.com"}',
                "{bad-json-line}",
                '{"network":"8.8.8.8","country":"United States","country_code":"US","continent":"North America","continent_code":"NA","asn":"AS15169","as_name":"Google LLC","as_domain":"google.com"}',
            ]
        ),
        encoding="utf-8",
    )

    adapter = IpGeolocationIpinfoJsonFileReaderAdapter()
    adapter_module = __import__(
        "infra.ip_geolocation.ip_geolocation_ipinfo_json_file_reader_adapter",
        fromlist=["DATASET_PATH"],
    )
    original_path = adapter_module.DATASET_PATH
    adapter_module.DATASET_PATH = data_file

    try:
        result = adapter.read_records()
    finally:
        adapter_module.DATASET_PATH = original_path

    assert result.total_lines == 3
    assert result.malformed_lines == 1
    assert len(result.records) == 2
    assert result.records[0].network == "1.1.1.0/24"
    assert result.records[1].network == "8.8.8.8/32"
