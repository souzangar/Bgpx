"""JSON-backed configuration service for background task wiring.

This service supports mtime-based in-memory reload. Configuration changes are
picked up when read again, but current task runtime reconciliation is out of
scope and is intentionally handled by next app lifespan/startup cycle.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


BACKGROUND_TASK_CONFIG_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "configs" / "background_tasks_config.json"
)

_CACHED_CONFIG: "BackgroundTasksConfig | None" = None
_CONFIG_MTIME_NS: int | None = None


@dataclass(frozen=True)
class IpGeolocationTaskConfig:
    """Validated one-task schedule configuration for IP geolocation domain."""

    task_key: str
    task_id: str
    interval_seconds: float
    resource_sequence: int
    enabled: bool
    stop_after_success: bool = False


@dataclass(frozen=True)
class IpGeolocationConfig:
    """Validated schedule configuration for IP geolocation background tasks."""

    resource_key: str
    tasks: tuple[IpGeolocationTaskConfig, ...]


@dataclass(frozen=True)
class BackgroundTasksConfig:
    """Top-level validated config model for background task settings."""

    version: int
    ip_geolocation: IpGeolocationConfig


def _read_config_mtime_ns() -> int | None:
    try:
        return BACKGROUND_TASK_CONFIG_PATH.stat().st_mtime_ns
    except OSError:
        return None


def _load_raw_config() -> dict[str, Any]:
    try:
        with BACKGROUND_TASK_CONFIG_PATH.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
    except Exception as exc:
        raise RuntimeError(
            f"Failed to load background task config from '{BACKGROUND_TASK_CONFIG_PATH}': {exc}"
        ) from exc

    if not isinstance(loaded, dict):
        raise RuntimeError(
            f"Background task config file '{BACKGROUND_TASK_CONFIG_PATH}' must contain a JSON object"
        )
    return loaded


def _require_dict(parent: dict[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise RuntimeError(f"background_tasks_config: '{key}' must be a JSON object")
    return value


def _require_non_empty_string(parent: dict[str, Any], key: str) -> str:
    value = parent.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"background_tasks_config: '{key}' must be a non-empty string")
    return value


def _require_positive_number(parent: dict[str, Any], key: str) -> float:
    value = parent.get(key)
    if not isinstance(value, (int, float)) or value <= 0:
        raise RuntimeError(f"background_tasks_config: '{key}' must be a number greater than 0")
    return float(value)


def _require_non_negative_integer(parent: dict[str, Any], key: str) -> int:
    value = parent.get(key)
    if not isinstance(value, int) or value < 0:
        raise RuntimeError(f"background_tasks_config: '{key}' must be an integer >= 0")
    return value


def _optional_bool(parent: dict[str, Any], key: str, default: bool) -> bool:
    value = parent.get(key, default)
    if not isinstance(value, bool):
        raise RuntimeError(f"background_tasks_config: '{key}' must be boolean")
    return value


def _parse_ip_geolocation_config(raw: dict[str, Any]) -> IpGeolocationConfig:
    ip_geo = _require_dict(raw, "ip_geolocation")
    resource_key = _require_non_empty_string(ip_geo, "resource_key")

    tasks_map = _require_dict(ip_geo, "tasks")
    parsed_tasks: list[IpGeolocationTaskConfig] = []

    for task_key, task_config_any in tasks_map.items():
        if not isinstance(task_key, str) or not task_key.strip():
            raise RuntimeError("background_tasks_config: all task keys must be non-empty strings")
        if not isinstance(task_config_any, dict):
            raise RuntimeError(
                f"background_tasks_config: task '{task_key}' must map to a JSON object"
            )

        task_id = _require_non_empty_string(task_config_any, "task_id")
        interval_seconds = _require_positive_number(task_config_any, "interval_seconds")
        resource_sequence = _require_non_negative_integer(task_config_any, "resource_sequence")
        enabled = _optional_bool(task_config_any, "enabled", True)
        stop_after_success = _optional_bool(task_config_any, "stop_after_success", False)

        parsed_tasks.append(
            IpGeolocationTaskConfig(
                task_key=task_key,
                task_id=task_id,
                interval_seconds=interval_seconds,
                resource_sequence=resource_sequence,
                enabled=enabled,
                stop_after_success=stop_after_success,
            )
        )

    task_ids = [task.task_id for task in parsed_tasks]
    if len(task_ids) != len(set(task_ids)):
        raise RuntimeError("background_tasks_config: duplicate task_id values are not allowed")

    return IpGeolocationConfig(resource_key=resource_key, tasks=tuple(parsed_tasks))


def _parse_config(raw: dict[str, Any]) -> BackgroundTasksConfig:
    version = raw.get("version")
    if not isinstance(version, int) or version <= 0:
        raise RuntimeError("background_tasks_config: 'version' must be a positive integer")

    return BackgroundTasksConfig(
        version=version,
        ip_geolocation=_parse_ip_geolocation_config(raw),
    )


def get_background_tasks_config() -> BackgroundTasksConfig:
    """Return validated background tasks config with mtime-based cache refresh."""
    global _CACHED_CONFIG, _CONFIG_MTIME_NS

    current_mtime_ns = _read_config_mtime_ns()
    if _CACHED_CONFIG is not None and _CONFIG_MTIME_NS == current_mtime_ns:
        return _CACHED_CONFIG

    parsed = _parse_config(_load_raw_config())
    _CACHED_CONFIG = parsed
    _CONFIG_MTIME_NS = current_mtime_ns
    return parsed


def reset_background_task_config_cache_for_tests() -> None:
    """Reset cached background task config state for test isolation."""
    global _CACHED_CONFIG, _CONFIG_MTIME_NS
    _CACHED_CONFIG = None
    _CONFIG_MTIME_NS = None


__all__ = [
    "BackgroundTasksConfig",
    "IpGeolocationConfig",
    "IpGeolocationTaskConfig",
    "get_background_tasks_config",
    "reset_background_task_config_cache_for_tests",
]