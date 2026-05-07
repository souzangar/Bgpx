"""Centralized backend logging configuration service."""

from __future__ import annotations

from copy import deepcopy
import json
import logging
import logging.config
import os
from pathlib import Path
from typing import Any

from models.logging import LoggingComponentConfigModel, parse_logging_components_config


VERBOSE_ENV = "BGPX_VERBOSE"
LOGGING_CONFIG_PATH = Path(__file__).resolve().parents[2] / "data" / "configs" / "logging_config.json"


_EVENT_REGISTRY: "LoggingEventConfigRegistry | None" = None
_LOGGING_CONFIG_MTIME_NS: int | None = None


def _resolve_log_level(level_text: str, default_level: int) -> int:
    """Resolve a logging level value from text with fallback."""
    normalized = level_text.strip().upper()
    resolved = logging.getLevelName(normalized)
    return resolved if isinstance(resolved, int) else default_level


def _is_verbose_enabled() -> bool:
    return os.getenv(VERBOSE_ENV, "0").strip().lower() in {"1", "true", "yes", "on"}


def _apply_named_logger_level(loggers: Any, logger_name: str, level: int) -> None:
    if not isinstance(loggers, dict):
        return
    logger_config = loggers.get(logger_name)
    if isinstance(logger_config, dict):
        logger_config["level"] = logging.getLevelName(level)


def _apply_verbose_levels(logging_config: dict[str, Any]) -> None:
    if not _is_verbose_enabled():
        return

    verbose_level = logging.INFO

    root_config = logging_config.get("root")
    if isinstance(root_config, dict):
        root_config["level"] = logging.getLevelName(verbose_level)

    loggers = logging_config.get("loggers")
    for logger_name in (
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
        "bgpx",
        "bgpx.tasks.ip_geo.refresher",
        "bgpx.tasks.ip_geo.ipinfo_gz_extractor",
        "bgpx.runner.background_task_runner",
    ):
        _apply_named_logger_level(loggers, logger_name, verbose_level)


def _load_logging_config() -> dict[str, Any]:
    """Load logging configuration from JSON config file."""
    try:
        with LOGGING_CONFIG_PATH.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
    except Exception as exc:
        raise RuntimeError(f"Failed to load logging config from '{LOGGING_CONFIG_PATH}': {exc}") from exc

    if not isinstance(loaded, dict):
        raise RuntimeError(f"Logging config file '{LOGGING_CONFIG_PATH}' must contain a JSON object")
    return loaded


def _read_logging_config_mtime_ns() -> int | None:
    """Read logging config mtime in ns, returning None if unavailable."""
    try:
        return LOGGING_CONFIG_PATH.stat().st_mtime_ns
    except OSError:
        return None


def _refresh_event_registry_if_needed() -> None:
    """Hot-reload component/event rules when logging JSON file changes."""
    global _EVENT_REGISTRY, _LOGGING_CONFIG_MTIME_NS

    current_mtime_ns = _read_logging_config_mtime_ns()
    if current_mtime_ns is None:
        return

    if _EVENT_REGISTRY is not None and _LOGGING_CONFIG_MTIME_NS == current_mtime_ns:
        return

    loaded_config = _load_logging_config()
    component_map = parse_logging_components_config(loaded_config.get("components"))
    _EVENT_REGISTRY = LoggingEventConfigRegistry(component_map)
    _LOGGING_CONFIG_MTIME_NS = current_mtime_ns


class LoggingEventConfigRegistry:
    """Runtime registry exposing component/event logging rules from JSON config."""

    def __init__(self, components: dict[str, LoggingComponentConfigModel]) -> None:
        self._components = components

    def is_component_enabled(self, component: str) -> bool:
        component_config = self._components.get(component)
        if component_config is None:
            return True
        return component_config.enabled

    def is_event_enabled(self, component: str, event_id: str) -> bool:
        component_config = self._components.get(component)
        if component_config is None:
            return True
        event_config = component_config.events.get(event_id)
        if event_config is None:
            return True
        return event_config.enabled

    def get_event_level(self, component: str, event_id: str, fallback_level: str) -> str:
        component_config = self._components.get(component)
        if component_config is None:
            return fallback_level

        event_config = component_config.events.get(event_id)
        if event_config is not None and event_config.level is not None:
            return event_config.level

        if component_config.default_level is not None:
            return component_config.default_level
        return fallback_level

    def get_component_logger_name(self, component: str, fallback_logger_name: str) -> str:
        component_config = self._components.get(component)
        if component_config is None:
            return fallback_logger_name
        if component_config.base_logger is not None:
            return component_config.base_logger
        return fallback_logger_name


class ComponentEventLogger:
    """Event-centric logger honoring component/event settings from JSON config."""

    def __init__(self, component: str, fallback_logger_name: str) -> None:
        self._component = component
        self._fallback_logger_name = fallback_logger_name

    def log(self, event_id: str, default_level: str, message: str, *args: object) -> None:
        _refresh_event_registry_if_needed()
        registry = get_logging_event_registry()
        if not registry.is_component_enabled(self._component):
            return
        if not registry.is_event_enabled(self._component, event_id):
            return

        logger_name = registry.get_component_logger_name(self._component, self._fallback_logger_name)
        logger = logging.getLogger(logger_name)
        level_text = registry.get_event_level(self._component, event_id, default_level)
        level = _resolve_log_level(level_text, _resolve_log_level(default_level, logging.INFO))
        logger.log(level, message, *args)

    def exception(self, event_id: str, message: str, *args: object) -> None:
        _refresh_event_registry_if_needed()
        registry = get_logging_event_registry()
        if not registry.is_component_enabled(self._component):
            return
        if not registry.is_event_enabled(self._component, event_id):
            return

        logger_name = registry.get_component_logger_name(self._component, self._fallback_logger_name)
        logger = logging.getLogger(logger_name)
        level_text = registry.get_event_level(self._component, event_id, "ERROR")
        level = _resolve_log_level(level_text, logging.ERROR)
        logger.log(level, message, *args, exc_info=True)


def get_component_event_logger(component: str, fallback_logger_name: str) -> ComponentEventLogger:
    return ComponentEventLogger(component=component, fallback_logger_name=fallback_logger_name)


def get_logging_event_registry() -> LoggingEventConfigRegistry:
    global _EVENT_REGISTRY
    if _EVENT_REGISTRY is None:
        _EVENT_REGISTRY = LoggingEventConfigRegistry(components={})
    return _EVENT_REGISTRY


def configure_backend_logging() -> None:
    """Apply unified logging config for backend + bgpx modules."""
    global _EVENT_REGISTRY, _LOGGING_CONFIG_MTIME_NS

    loaded_config = _load_logging_config()
    logging_config = deepcopy(loaded_config)
    _apply_verbose_levels(logging_config)

    component_map = parse_logging_components_config(loaded_config.get("components"))
    _EVENT_REGISTRY = LoggingEventConfigRegistry(component_map)
    _LOGGING_CONFIG_MTIME_NS = _read_logging_config_mtime_ns()
    logging.config.dictConfig(logging_config)


__all__ = ["configure_backend_logging", "get_component_event_logger"]
