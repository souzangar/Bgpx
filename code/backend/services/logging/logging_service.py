"""Centralized backend logging configuration service."""

from __future__ import annotations

import logging
import logging.config
import os


VERBOSE_ENV = "BGPX_VERBOSE"
IP_GEO_REFRESHER_LOG_LEVEL_ENV = "BGPX_LOG_LEVEL_IP_GEO_REFRESHER"
IP_GEO_DOWNLOADER_LOG_LEVEL_ENV = "BGPX_LOG_LEVEL_IP_GEO_DOWNLOADER"
BG_RUNNER_LOG_LEVEL_ENV = "BGPX_LOG_LEVEL_BG_RUNNER"


def _resolve_log_level(level_text: str, default_level: int) -> int:
    """Resolve a logging level value from text with fallback."""
    normalized = level_text.strip().upper()
    resolved = logging.getLevelName(normalized)
    return resolved if isinstance(resolved, int) else default_level


def _is_verbose_enabled() -> bool:
    return os.getenv(VERBOSE_ENV, "0").strip().lower() in {"1", "true", "yes", "on"}


def configure_backend_logging() -> None:
    """Apply unified logging config for backend + bgpx modules."""
    verbose_enabled = _is_verbose_enabled()
    default_level = logging.INFO if verbose_enabled else logging.WARNING
    default_level_text = "INFO" if verbose_enabled else "WARNING"

    refresher_level = _resolve_log_level(
        os.getenv(IP_GEO_REFRESHER_LOG_LEVEL_ENV, default_level_text),
        default_level,
    )
    downloader_level = _resolve_log_level(
        os.getenv(IP_GEO_DOWNLOADER_LOG_LEVEL_ENV, default_level_text),
        default_level,
    )
    bg_runner_level = _resolve_log_level(
        os.getenv(BG_RUNNER_LOG_LEVEL_ENV, default_level_text),
        default_level,
    )

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {
                    "format": "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "standard",
                    "level": "NOTSET",
                }
            },
            "root": {
                "handlers": ["console"],
                "level": logging.getLevelName(default_level),
            },
            "loggers": {
                "uvicorn": {"level": logging.getLevelName(default_level), "propagate": True},
                "uvicorn.error": {"level": logging.getLevelName(default_level), "propagate": True},
                "uvicorn.access": {"level": logging.getLevelName(default_level), "propagate": True},
                "bgpx": {"level": logging.getLevelName(default_level), "propagate": True},
                "bgpx.tasks.ip_geo.refresher": {
                    "level": logging.getLevelName(refresher_level),
                    "propagate": True,
                },
                "bgpx.tasks.ip_geo.downloader": {
                    "level": logging.getLevelName(downloader_level),
                    "propagate": True,
                },
                "bgpx.runner.background_task_runner": {
                    "level": logging.getLevelName(bg_runner_level),
                    "propagate": True,
                },
            },
        }
    )
