# Background Task Runner Service (`background_task_runner` package)

This document describes the **current implemented state** of the background task runner subsystem.

Location:
- Service package: `code/backend/services/background_task_runner/`
- Runtime core: `code/backend/services/background_task_runner/background_task_runner.py`
- Config service: `code/backend/services/background_task_runner/background_task_config_service.py`
- FastAPI lifespan wiring: `code/backend/services/background_task_runner/ip_geolocation_lifespan.py`
- Shared models: `code/backend/models/background_task_runner/background_task_runner_models.py`

---

## 1) Purpose

The background task runner is a **domain-agnostic runtime orchestrator** that manages process-local periodic/background jobs.

It is responsible for:
- task registration/unregistration,
- per-task loop start/stop lifecycle,
- overlap prevention,
- bounded retry/backoff after failures,
- observable per-task runtime status,
- in-process singleton ownership for app lifespan wiring.

Domain-specific logic (e.g. IP geolocation dataset downloader/extractor/refresh behavior) remains outside the runner.

---

## 2) Package Surface and Exports

`services/background_task_runner/__init__.py` exports:
- model contracts from `models.background_task_runner`:
  - `BackgroundTaskDefinition`, `BackgroundTaskStatus`
  - `RetryBackoffConfig`, `OverlapPolicy`
  - `TaskCallable` (+ sync/async aliases)
- runtime API:
  - `BackgroundTaskRunner`
  - `get_background_task_runner()`
  - `reset_background_task_runner_for_tests()`
- app lifespan hook:
  - `app_lifespan`

This makes the package a single integration boundary for startup wiring and tests.

---

## 3) Task Contract (Implemented)

From `background_task_runner_models.py`:

- `BackgroundTaskDefinition`
  - `task_id: str` (unique, non-empty)
  - `interval_seconds: float` (> 0)
  - `run_once: TaskCallable` (sync or async)
  - `resource_key: str` (non-empty)
  - `resource_sequence: int` (>= 0)
  - `stop_after_success: bool` (one-shot behavior)
  - `overlap_policy: OverlapPolicy` (default `SKIP_IF_RUNNING`)
  - `retry_backoff: RetryBackoffConfig`

- `BackgroundTaskStatus`
  - `is_running`
  - `last_run_started_at`
  - `last_run_succeeded_at`
  - `last_error_message`
  - `consecutive_failure_count`
  - `total_runs`
  - `skipped_overlap_runs`

Validation is performed in model `__post_init__` methods.

---

## 4) Runtime Behavior (Implemented)

### 4.1 Registry and lifecycle

`BackgroundTaskRunner` keeps:
- registry keyed by `task_id`,
- resource-group state keyed by `resource_key`,
- runner lifecycle flag,
- task loop/run handles,
- sync executor for non-async callables.

Public lifecycle API:
- `start_background_task_runner()` / `stop_background_task_runner()` (idempotent)
- `register_background_task(task)` / `unregister_background_task(task_id)`
- `start_background_task(task_id)` / `stop_background_task(task_id)` (idempotent)
- `get_background_task_status(task_id)`

### 4.2 Scheduling and overlap

Per task:
- one loop coroutine (`_run_registered_task_loop`) ticks by `interval_seconds`.

Current overlap behavior:
- effective safe behavior is skip-if-running,
- `OverlapPolicy` enum includes `QUEUE_ONE` and `RESTART`, but these are currently future-ready contract values; runner behavior remains conservative skip semantics.

### 4.3 Resource-group sequencing

Tasks sharing the same `resource_key` are sequenced by:
1. `resource_sequence` ascending,
2. `task_id` lexical tie-break.

Resource-group coordination includes:
- `active_task_id` lock-like ownership,
- `next_task_id_turn` rotation,
- normalization of turn pointer,
- immediate peer scheduling after run completion to reduce starvation/phase-alignment delays.

### 4.4 Failure handling and backoff

Run failures are contained per task and update status:
- increment `consecutive_failure_count`,
- set `last_error_message`,
- compute bounded exponential backoff with jitter,
- set `next_eligible_run_at_monotonic`.

On success:
- set `last_run_succeeded_at`,
- clear `last_error_message`,
- reset `consecutive_failure_count`,
- clear backoff delay.

### 4.5 One-shot task behavior

If `stop_after_success=True`, task loop is marked stopped after first successful run (without cancelling its currently running execution). This is used by the bootstrap IP geolocation task.

---

## 5) Config Service (`background_task_config_service.py`)

Configuration source:
- `code/backend/data/configs/background_tasks_config.json`

Service guarantees:
- strict JSON shape validation,
- typed dataclass projection:
  - `BackgroundTasksConfig`
  - `IpGeolocationConfig`
  - `IpGeolocationTaskConfig`
- mtime-based in-memory cache refresh (`get_background_tasks_config()`),
- explicit test reset hook (`reset_background_task_config_cache_for_tests()`).

Current config supports:
- top-level `version`,
- `ip_geolocation.resource_key`,
- task map entries with:
  - `task_id`, `interval_seconds`, `resource_sequence`, `enabled`, `stop_after_success`.

---

## 6) FastAPI Lifespan Wiring (Current)

`main.py` wires app lifespan via:
- `from services.background_task_runner.ip_geolocation_lifespan import app_lifespan`
- `FastAPI(..., lifespan=app_lifespan)`

`ip_geolocation_lifespan.py` startup flow:
1. start runner,
2. initialize IP geolocation service dataset,
3. build downloader + extractor + refresher domain services,
4. load validated config,
5. map configured task keys to callables,
6. register enabled tasks idempotently,
7. start enabled tasks.

Resource-key mapping detail for IP geolocation tasks:
- base resource key comes from config (`ip_geolocation.resource_key`),
- `ipinfo_gz_extractor` and `data_refresh` remain in the base resource group,
- `ipinfo_gz_downloader` is intentionally isolated to
  `"<base_resource_key>:downloader"` so its long polling interval does not gate
  extractor/refresh short-cadence scheduling.

Shutdown flow:
1. stop enabled tasks idempotently,
2. unregister enabled tasks idempotently,
3. stop runner.

Required task keys expected in config:
- `bootstrap_once`
- `ipinfo_gz_downloader`
- `ipinfo_gz_extractor`
- `data_refresh`

If none are enabled, startup raises runtime error.

---

## 7) Testing Coverage (Current)

Key tests include:

- Unit:
  - `code/backend/tests/unit/test_background_task_runner.py`
  - `code/backend/tests/unit/test_background_task_config_service.py`

- Integration:
  - `code/backend/tests/integration/test_app_lifespan_background_task_runner.py`

Integration scenarios verify:
- app lifespan starts/stops runner,
- IP geolocation tasks are running during app lifetime,
- tasks are cleaned on shutdown,
- bootstrap task stops after first successful run while sequenced periodic tasks continue.

---

## 8) Design Boundaries and Notes

- Runner package remains reusable and domain-agnostic.
- Domain work stays in `services/ip_geolocation/*`.
- Lifecycle orchestration for domain tasks lives in dedicated lifespan module (`ip_geolocation_lifespan.py`), not in `main.py` directly.
- Runtime is in-process; with multi-worker deployment, each worker would own its own runner unless explicit cross-process coordination is introduced.

---

## 9) Quick Reference

- Start runner: `runner.start_background_task_runner()`
- Register: `runner.register_background_task(task_def)`
- Start task: `runner.start_background_task(task_id)`
- Read status: `runner.get_background_task_status(task_id)`
- Stop task: `runner.stop_background_task(task_id)`
- Unregister: `runner.unregister_background_task(task_id)`
- Stop runner: `runner.stop_background_task_runner()`

For app wiring, prefer using exported `app_lifespan` rather than duplicating lifecycle logic in `main.py`.
