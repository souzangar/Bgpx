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
        if not isinstance(component_name, str) or not component_name.strip():
            continue
        if not isinstance(component_value, dict):
            continue

        raw_events = component_value.get("events")
        parsed_events: dict[str, LoggingEventConfigModel] = {}
        if isinstance(raw_events, dict):
            for event_id, event_value in raw_events.items():
                if not isinstance(event_id, str) or not event_id.strip():
                    continue
                if not isinstance(event_value, dict):
                    continue

                parsed_events[event_id] = LoggingEventConfigModel(
                    enabled=bool(event_value.get("enabled", True)),
                    level=event_value.get("level") if isinstance(event_value.get("level"), str) else None,
                )

        parsed[component_name] = LoggingComponentConfigModel(
            enabled=bool(component_value.get("enabled", True)),
            default_level=(
                component_value.get("default_level")
                if isinstance(component_value.get("default_level"), str)
                else None
            ),
            base_logger=(
                component_value.get("base_logger") if isinstance(component_value.get("base_logger"), str) else None
            ),
            events=parsed_events,
        )

    return parsed


__all__ = [
    "LoggingComponentConfigModel",
    "LoggingEventConfigModel",
    "parse_logging_components_config",
]
