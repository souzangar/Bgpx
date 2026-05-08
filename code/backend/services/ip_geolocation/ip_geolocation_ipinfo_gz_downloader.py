"""IPinfo .gz downloader for IP geolocation dataset.

This component downloads the provider file using API token loaded from a
dedicated JSON config file and atomically replaces the target .gz file.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import shutil
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from typing import Callable

import httpx

from services.logging.logging_service import get_component_event_logger


DOWNLOADER_CONFIG_PATH = Path(
    "code/backend/data/configs/ip_geolocation_ipinfo_gz_downloader_config.json"
)
DOWNLOADER_OUTPUT_PATH = Path("code/backend/data/ip_geolocation/ipinfo_lite.json.gz")
DOWNLOADER_TEMP_PATH = Path("code/backend/data/ip_geolocation/ipinfo_lite.json.gz.tmp")
IPINFO_URL_TEMPLATE = "https://ipinfo.io/data/ipinfo_lite.json.gz?_src=frontend&token={token}"

event_logger = get_component_event_logger(
    "ip_geo_ipinfo_gz_downloader",
    "bgpx.tasks.ip_geo.ipinfo_gz_downloader",
)


@dataclass(frozen=True)
class IpinfoDownloaderConfig:
    """Validated downloader config loaded from dedicated JSON file."""

    api_token: str


class IpGeolocationIpinfoGzDownloader:
    """Download IPinfo .gz into backend data path with atomic replace."""

    def __init__(
        self,
        *,
        config_path: Path = DOWNLOADER_CONFIG_PATH,
        output_path: Path = DOWNLOADER_OUTPUT_PATH,
        temp_path: Path = DOWNLOADER_TEMP_PATH,
        http_get: Callable[..., httpx.Response] = httpx.get,
    ) -> None:
        self._config_path = config_path
        self._output_path = output_path
        self._temp_path = temp_path
        self._http_get = http_get

        self.last_download_error: str | None = None
        self.last_download_attempt_at: datetime | None = None
        self.last_download_succeeded_at: datetime | None = None
        self.download_attempt_count: int = 0
        self.download_success_count: int = 0
        self.download_failure_count: int = 0

    def run_once(self) -> None:
        """Execute one downloader cycle."""
        self.download_attempt_count += 1
        self.last_download_attempt_at = datetime.now(UTC)

        try:
            config = self._load_config()
            url = IPINFO_URL_TEMPLATE.format(token=config.api_token)

            event_logger.log("download_started", "INFO", "IPinfo .gz download started")
            response = self._http_get(url, timeout=120.0, follow_redirects=True)
            response.raise_for_status()

            self._write_response_atomically(response.content)

            self.last_download_error = None
            self.last_download_succeeded_at = datetime.now(UTC)
            self.download_success_count += 1
            event_logger.log(
                "download_succeeded",
                "INFO",
                "IPinfo .gz download succeeded (output=%s)",
                self._output_path,
            )
        except httpx.HTTPStatusError as exc:
            self.last_download_error = self._sanitize_sensitive_text(str(exc)) or exc.__class__.__name__
            self.download_failure_count += 1
            status_code = exc.response.status_code
            if status_code == 401:
                event_logger.log(
                    "download_failed",
                    "ERROR",
                    "IPinfo .gz download unauthorized (failure_count=%s): invalid API token",
                    self.download_failure_count,
                )
            else:
                event_logger.log(
                    "download_failed",
                    "ERROR",
                    "IPinfo .gz download failed (failure_count=%s, status_code=%s): %s",
                    self.download_failure_count,
                    status_code,
                    self.last_download_error,
                )
            self._delete_temp_if_exists()
        except Exception as exc:
            self.last_download_error = self._sanitize_sensitive_text(str(exc)) or exc.__class__.__name__
            self.download_failure_count += 1
            event_logger.log(
                "download_failed",
                "ERROR",
                "IPinfo .gz download failed (failure_count=%s): %s",
                self.download_failure_count,
                self.last_download_error,
            )
            self._delete_temp_if_exists()

    def _sanitize_sensitive_text(self, text: str) -> str:
        """Redact sensitive query parameters if present in free-form text."""
        if not text:
            return text

        token_marker = "token="
        if token_marker not in text:
            return text

        split_text = text.split()
        sanitized_parts: list[str] = []
        for part in split_text:
            sanitized_parts.append(self._sanitize_url_token(part))
        return " ".join(sanitized_parts)

    def _sanitize_url_token(self, value: str) -> str:
        """Redact token query parameter in URL-like values."""
        if "token=" not in value:
            return value

        try:
            parsed = urlsplit(value)
            if not parsed.query:
                return value

            redacted_items: list[tuple[str, str]] = []
            for key, item_value in parse_qsl(parsed.query, keep_blank_values=True):
                if key.lower() == "token":
                    redacted_items.append((key, "<REDACTED>"))
                else:
                    redacted_items.append((key, item_value))

            redacted_query = urlencode(redacted_items)
            return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, redacted_query, parsed.fragment))
        except Exception:
            return value

    def _load_config(self) -> IpinfoDownloaderConfig:
        try:
            raw = json.loads(self._config_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise RuntimeError("missing token config file") from exc
        except Exception as exc:
            raise RuntimeError(f"Failed to load downloader config '{self._config_path}': {exc}") from exc

        if not isinstance(raw, dict):
            raise RuntimeError("ipinfo downloader config must be a JSON object")

        if "api_token" not in raw:
            raise RuntimeError("api_token key not found in config file")

        api_token = raw.get("api_token")
        if not isinstance(api_token, str) or not api_token.strip():
            raise RuntimeError("ipinfo downloader config: 'api_token' must be a non-empty string")

        return IpinfoDownloaderConfig(api_token=api_token)

    def _write_response_atomically(self, content: bytes) -> None:
        self._temp_path.parent.mkdir(parents=True, exist_ok=True)
        with self._temp_path.open("wb") as temp_handle:
            temp_handle.write(content)

        self._output_path.parent.mkdir(parents=True, exist_ok=True)
        with self._temp_path.open("rb") as source_handle:
            with self._output_path.open("wb") as target_handle:
                shutil.copyfileobj(source_handle, target_handle)

        self._delete_temp_if_exists()

    def _delete_temp_if_exists(self) -> None:
        if self._temp_path.exists():
            self._temp_path.unlink()


__all__ = [
    "DOWNLOADER_CONFIG_PATH",
    "DOWNLOADER_OUTPUT_PATH",
    "DOWNLOADER_TEMP_PATH",
    "IpGeolocationIpinfoGzDownloader",
    "IpinfoDownloaderConfig",
]
