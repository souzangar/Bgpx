# Logging Service Plan (`logging_service.py`)

This document defines the design and behavior contract for the backend centralized logging service.

Target location:
- Service doc: `code/backend/services/logging/README.md`
- Service module: `code/backend/services/logging/logging_service.py`
- Logging config source: `code/backend/data/configs/logging_config.json`

---

## 1) Purpose

`logging_service.py` provides unified logging setup and event-level logging controls for backend components.

Primary goals:
- Load logging configuration from a JSON file
- Apply global logging settings via `logging.config.dictConfig`
- Support runtime verbose mode (`BGPX_VERBOSE`)
- Provide component/event-aware logging through a registry
- Support hot-reload of component/event logging rules when config file changes

---

## 2) Layer Position and Boundaries

Expected architecture flow:

`api -> apps -> services -> infra/models`

`logging_service` is a cross-cutting service utility under `services` and should be consumed by runtime modules that need structured logging behavior.

Boundary rules:
- Keep logging orchestration in this service.
- Keep transport concerns (HTTP response decisions) outside this module.
- Keep config-driven event policy here, not duplicated in domain services.

---

## 3) Configuration Contract

### 3.1 Config file path

The service uses a fixed path constant:

- `LOGGING_CONFIG_PATH = code/backend/data/configs/logging_config.json`

### 3.2 Environment variables

- `BGPX_VERBOSE`
  - truthy values: `1`, `true`, `yes`, `on` (case-insensitive)
  - when enabled, selected logger levels are elevated to `INFO`

### 3.3 Config structure expectations

The JSON file must be a top-level object compatible with `logging.config.dictConfig`.

Optional custom section supported by this service:
- `components` (object)
  - component-level enable/disable
  - per-event enable/disable
  - per-event level override
  - component default level
  - component base logger override

---

## 4) Core Runtime Behaviors

### 4.1 Backend logging setup

`configure_backend_logging()`:
- Loads JSON config
- Applies verbose overrides (if enabled)
- Builds component event registry from `components`
- Stores config file mtime in ns for reload checks
- Applies final config through `logging.config.dictConfig`

### 4.2 Verbose mode behavior

When verbose is enabled, service sets `INFO` level for:
- root logger
- `uvicorn`
- `uvicorn.error`
- `uvicorn.access`
- `bgpx`
- `bgpx.tasks.ip_geo.refresher`
- `bgpx.tasks.ip_geo.downloader`
- `bgpx.runner.background_task_runner`

### 4.3 Event registry hot-reload

Before component-event logs are emitted, service checks whether logging config file mtime changed.

If changed:
- reload config
- rebuild `LoggingEventConfigRegistry`
- update stored mtime

If unchanged:
- continue with cached registry

---

## 5) Public Interface

### 5.1 Exported API

- `configure_backend_logging()`
- `get_component_event_logger(component: str, fallback_logger_name: str)`

### 5.2 Registry access

- `get_logging_event_registry()` returns active registry
- initializes empty default registry if config has not been loaded yet

---

## 6) Component/Event Logging Model

### 6.1 `LoggingEventConfigRegistry`

Provides config-driven policy methods:
- `is_component_enabled(component)`
- `is_event_enabled(component, event_id)`
- `get_event_level(component, event_id, fallback_level)`
- `get_component_logger_name(component, fallback_logger_name)`

Default behavior is permissive when config entries are missing.

### 6.2 `ComponentEventLogger`

Provides event-centric logging methods:
- `log(event_id, default_level, message, *args)`
- `exception(event_id, message, *args)`

Behavior:
- refresh registry if needed
- check component/event enabled flags
- resolve logger name and level from registry/fallbacks
- emit message using resolved level
- include `exc_info=True` for `exception(...)`

---

## 7) Error Handling Contract

- Config load errors raise `RuntimeError` with file path context.
- Non-object JSON config raises `RuntimeError`.
- Missing/unreadable mtime during hot-reload check is handled safely (no crash, no reload attempt).

---

## 8) Testing Guidance

Recommended unit coverage for `logging_service.py`:
- `_resolve_log_level` fallback behavior
- `_is_verbose_enabled` truthy parsing
- `_apply_verbose_levels` logger level overrides
- `_load_logging_config` success/failure paths
- registry defaults when component/event entries are missing
- component/event enable-disable decisions
- `ComponentEventLogger.log` and `.exception` behavior
- hot-reload behavior when mtime changes vs unchanged

Integration-level checks:
- backend startup applies config without errors
- verbose mode changes expected logger levels
- event filtering from `components` config affects runtime logs deterministically

---

## 9) Implementation/Change Checklist

- [ ] Keep all logging policy logic centralized in `services/logging/logging_service.py`
- [ ] Keep JSON config schema backward-compatible when extending `components`
- [ ] Never duplicate event-level filtering logic across domain services
- [ ] Keep public exports minimal and explicit
- [ ] Add/update tests when changing registry or verbose behavior

---

## 10) Summary

This logging service provides a centralized and configurable logging foundation for backend runtime behavior, including:
- unified config application,
- component/event-level controls,
- optional verbose mode,
- lightweight hot-reload of logging event rules.
