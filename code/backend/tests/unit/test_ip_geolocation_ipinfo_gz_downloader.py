"""Unit tests for IP geolocation IPinfo .gz downloader."""

from __future__ import annotations

from pathlib import Path
import sys

import httpx
import pytest


BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.ip_geolocation.ip_geolocation_ipinfo_gz_downloader import (  # noqa: E402
    IpGeolocationIpinfoGzDownloader,
)


def test_downloader_downloads_with_token_and_writes_output(tmp_path: Path) -> None:
    """Downloader should build URL from token config and write output file."""
    config_path = tmp_path / "downloader_config.json"
    output_path = tmp_path / "ipinfo_lite.json.gz"
    temp_path = tmp_path / "ipinfo_lite.json.gz.tmp"
    config_path.write_text('{"api_token": "abc123"}', encoding="utf-8")

    captured: dict[str, object] = {}

    def _http_get(url: str, timeout: float) -> httpx.Response:
        captured["url"] = url
        captured["timeout"] = timeout
        return httpx.Response(
            status_code=200,
            content=b"gz-bytes",
            request=httpx.Request("GET", url),
        )

    downloader = IpGeolocationIpinfoGzDownloader(
        config_path=config_path,
        output_path=output_path,
        temp_path=temp_path,
        http_get=_http_get,
    )

    downloader.run_once()

    assert captured["url"] == "https://ipinfo.io/data/ipinfo_lite.json.gz?_src=frontend&token=abc123"
    assert captured["timeout"] == pytest.approx(120.0)
    assert output_path.read_bytes() == b"gz-bytes"
    assert temp_path.exists() is False
    assert downloader.download_success_count == 1
    assert downloader.download_failure_count == 0


def test_downloader_fails_when_token_missing(tmp_path: Path) -> None:
    """Missing api_token key should return explicit missing-key error message."""
    config_path = tmp_path / "downloader_config.json"
    output_path = tmp_path / "ipinfo_lite.json.gz"
    temp_path = tmp_path / "ipinfo_lite.json.gz.tmp"
    config_path.write_text("{}", encoding="utf-8")

    downloader = IpGeolocationIpinfoGzDownloader(
        config_path=config_path,
        output_path=output_path,
        temp_path=temp_path,
        http_get=lambda *_args, **_kwargs: httpx.Response(
            status_code=200,
            content=b"unused",
            request=httpx.Request("GET", "https://example.test"),
        ),
    )

    downloader.run_once()

    assert downloader.download_attempt_count == 1
    assert downloader.download_success_count == 0
    assert downloader.download_failure_count == 1
    assert downloader.last_download_error == "api_token key not found in config file"
    assert output_path.exists() is False


def test_downloader_unauthorized_logs_single_line_without_traceback(caplog, tmp_path: Path) -> None:
    """401 unauthorized should be logged as a concise single-line message."""
    config_path = tmp_path / "downloader_config.json"
    output_path = tmp_path / "ipinfo_lite.json.gz"
    temp_path = tmp_path / "ipinfo_lite.json.gz.tmp"
    config_path.write_text('{"api_token": "bad-token"}', encoding="utf-8")

    def _http_get(url: str, timeout: float) -> httpx.Response:
        request = httpx.Request("GET", url)
        response = httpx.Response(status_code=401, request=request)
        raise httpx.HTTPStatusError("401 unauthorized", request=request, response=response)

    downloader = IpGeolocationIpinfoGzDownloader(
        config_path=config_path,
        output_path=output_path,
        temp_path=temp_path,
        http_get=_http_get,
    )

    with caplog.at_level("ERROR", logger="bgpx.tasks.ip_geo.ipinfo_gz_downloader"):
        downloader.run_once()

    assert downloader.download_attempt_count == 1
    assert downloader.download_failure_count == 1
    assert downloader.download_success_count == 0
    assert downloader.last_download_error is not None
    assert "401" in downloader.last_download_error

    messages = [record.getMessage() for record in caplog.records]
    assert any("download unauthorized" in message for message in messages)
    assert all("Traceback" not in message for message in messages)


def test_downloader_missing_config_file_returns_normalized_message(tmp_path: Path) -> None:
    """Missing config file should return a concise semantic error message."""
    missing_config_path = tmp_path / "missing-downloader-config.json"
    output_path = tmp_path / "ipinfo_lite.json.gz"
    temp_path = tmp_path / "ipinfo_lite.json.gz.tmp"

    downloader = IpGeolocationIpinfoGzDownloader(
        config_path=missing_config_path,
        output_path=output_path,
        temp_path=temp_path,
        http_get=lambda *_args, **_kwargs: httpx.Response(
            status_code=200,
            content=b"unused",
            request=httpx.Request("GET", "https://example.test"),
        ),
    )

    downloader.run_once()

    assert downloader.download_attempt_count == 1
    assert downloader.download_success_count == 0
    assert downloader.download_failure_count == 1
    assert downloader.last_download_error == "missing token config file"
