"""Unit tests for logging models parsing and service registry behavior."""

from __future__ import annotations

from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from models.logging import LoggingComponentConfigModel, parse_logging_components_config  # noqa: E402
from services.logging.logging_service import LoggingEventConfigRegistry  # noqa: E402


def test_parse_logging_components_config_returns_typed_models() -> None:
    """Parser should map raw component/event config into typed DTOs."""
    parsed = parse_logging_components_config(
        {
            "ip_geo_refresher": {
                "enabled": True,
                "default_level": "WARNING",
                "base_logger": "bgpx.tasks.ip_geo.refresher",
                "events": {
                    "refresh_started": {"enabled": True, "level": "INFO"},
                    "refresh_failed": {"enabled": False, "level": "ERROR"},
                },
            }
        }
    )

    component = parsed["ip_geo_refresher"]
    assert isinstance(component, LoggingComponentConfigModel)
    assert component.enabled is True
    assert component.default_level == "WARNING"
    assert component.base_logger == "bgpx.tasks.ip_geo.refresher"
    assert component.events["refresh_started"].level == "INFO"
    assert component.events["refresh_failed"].enabled is False


def test_registry_uses_typed_models_for_event_decisions() -> None:
    """Service registry should honor typed model fields for enable/level/logger logic."""
    component_map = parse_logging_components_config(
        {
            "ip_geo_refresher": {
                "enabled": True,
                "default_level": "WARNING",
                "base_logger": "bgpx.tasks.ip_geo.refresher",
                "events": {
                    "refresh_started": {"enabled": True, "level": "INFO"},
                    "refresh_failed": {"enabled": False, "level": "ERROR"},
                },
            }
        }
    )
    registry = LoggingEventConfigRegistry(component_map)

    assert registry.is_component_enabled("ip_geo_refresher") is True
    assert registry.is_event_enabled("ip_geo_refresher", "refresh_started") is True
    assert registry.is_event_enabled("ip_geo_refresher", "refresh_failed") is False
    assert registry.get_event_level("ip_geo_refresher", "refresh_started", "DEBUG") == "INFO"
    assert registry.get_event_level("ip_geo_refresher", "unknown_event", "DEBUG") == "WARNING"
    assert (
        registry.get_component_logger_name("ip_geo_refresher", "fallback.logger")
        == "bgpx.tasks.ip_geo.refresher"
    )
