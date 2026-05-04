"""Unit tests for IP geolocation NDJSON parser behavior."""

from __future__ import annotations

from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from infra.ip_geolocation import parse_ipinfo_ndjson_lines


def test_parse_ipinfo_ndjson_lines_parses_valid_record() -> None:
    """Parser should map one valid NDJSON line to one normalized record."""
    lines = [
        '{"network":"1.0.0.0/24","country":"Australia","country_code":"AU","continent":"Oceania","continent_code":"OC","asn":"AS13335","as_name":"Cloudflare, Inc.","as_domain":"cloudflare.com"}'
    ]

    parsed = parse_ipinfo_ndjson_lines(lines)

    assert parsed.malformed_count == 0
    assert len(parsed.records) == 1
    assert parsed.records[0].network == "1.0.0.0/24"
    assert parsed.records[0].asn == "AS13335"


def test_parse_ipinfo_ndjson_lines_normalizes_host_ip_to_32() -> None:
    """Host-only IP network values should be normalized to /32."""
    lines = [
        '{"network":"1.7.168.172","country":"Australia","country_code":"AU","continent":"Oceania","continent_code":"OC","asn":null,"as_name":null,"as_domain":null}'
    ]

    parsed = parse_ipinfo_ndjson_lines(lines)

    assert parsed.malformed_count == 0
    assert len(parsed.records) == 1
    assert parsed.records[0].network == "1.7.168.172/32"
    assert parsed.records[0].asn is None


def test_parse_ipinfo_ndjson_lines_counts_malformed_and_skips_empty_lines() -> None:
    """Malformed lines should increment counter while valid lines still parse."""
    lines = [
        "",
        "   ",
        "{not-json}",
        '{"network":"8.8.8.0/24","country":"United States","country_code":"US","continent":"North America","continent_code":"NA","asn":"AS15169","as_name":"Google LLC","as_domain":"google.com"}',
    ]

    parsed = parse_ipinfo_ndjson_lines(lines)

    assert parsed.malformed_count == 1
    assert len(parsed.records) == 1
    assert parsed.records[0].network == "8.8.8.0/24"
