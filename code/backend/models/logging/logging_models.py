"""Shared models for logging configuration contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class LoggingEventConfigModel:
    """Per-event logging policy contract."""

    enabled: bool = True
    level: str | None = None

    def __post_init__(self) -> None:
        """Validate optional event-level override values."""
        if self.level is not None and not self.level.strip():
            raise ValueError("level must be a non-empty string when provided")


@dataclass(frozen=True)
class LoggingComponentConfigModel:
    """Per-component logging policy contract."""

    enabled: bool = True
    default_level: str | None = None
    base_logger: str | None = None
    events: dict[str, LoggingEventConfigModel] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate optional component-level override values."""
        if self.default_level is not None and not self.default_level.strip():
            raise ValueError("default_level must be a non-empty string when provided")

        if self.base_logger is not None and not self.base_logger.strip():
            raise ValueError("base_logger must be a non-empty string when provided")

        for event_id in self.events:
            if not event_id.strip():
                raise ValueError("event_id keys must be non-empty strings")


def parse_logging_components_config(raw_components: Any) -> dict[str, LoggingComponentConfigModel]:
    """Parse raw JSON component config into strict logging component models."""
    if not isinstance(raw_components, dict):
        return {}

    parsed: dict[str, LoggingComponentConfigModel] = {}
    for component_name, component_value in raw_components.items():
        normalized_component_name = _as_non_empty_str(component_name)
        if normalized_component_name is None:
            continue

        parsed_component = _parse_logging_component_config(component_value)
        if parsed_component is None:
            continue

        parsed[normalized_component_name] = parsed_component

    return parsed


def _as_non_empty_str(raw_value: Any) -> str | None:
    """Return a string only when the raw value is a non-empty string."""
    if not isinstance(raw_value, str):
        return None
    if not raw_value.strip():
        return None
    return raw_value


def _as_optional_str(raw_value: Any) -> str | None:
    """Return a string only when raw value is a string; otherwise None."""
    return raw_value if isinstance(raw_value, str) else None


def _parse_logging_event_config(raw_event_value: Any) -> LoggingEventConfigModel | None:
    """Parse and validate a raw event config object."""
    if not isinstance(raw_event_value, dict):
        return None

    return LoggingEventConfigModel(
        enabled=bool(raw_event_value.get("enabled", True)),
        level=_as_optional_str(raw_event_value.get("level")),
    )


def _parse_logging_events(raw_events: Any) -> dict[str, LoggingEventConfigModel]:
    """Parse event map into validated event config models."""
    if not isinstance(raw_events, dict):
        return {}

    parsed_events: dict[str, LoggingEventConfigModel] = {}
    for raw_event_id, raw_event_value in raw_events.items():
        event_id = _as_non_empty_str(raw_event_id)
        if event_id is None:
            continue

        parsed_event = _parse_logging_event_config(raw_event_value)
        if parsed_event is None:
            continue

        parsed_events[event_id] = parsed_event

    return parsed_events


def _parse_logging_component_config(raw_component_value: Any) -> LoggingComponentConfigModel | None:
    """Parse and validate a raw component config object."""
    if not isinstance(raw_component_value, dict):
        return None

    return LoggingComponentConfigModel(
        enabled=bool(raw_component_value.get("enabled", True)),
        default_level=_as_optional_str(raw_component_value.get("default_level")),
        base_logger=_as_optional_str(raw_component_value.get("base_logger")),
        events=_parse_logging_events(raw_component_value.get("events")),
    )


__all__ = [
    "LoggingComponentConfigModel",
    "LoggingEventConfigModel",
    "parse_logging_components_config",
]
