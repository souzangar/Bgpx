# Background Task Runner Service Plan (`background_task_runner.py`)

This document defines the design and implementation plan for the generic backend background task runner service.

Location target:
- Service doc: `code/backend/services/background_task_runner_service.md`
- Planned service module:
  - `code/backend/services/background_task_runner/background_task_runner.py`
  - `code/backend/services/background_task_runner/task_contracts.py` (optional)

Related docs:
- IP geolocation integration plan: `code/backend/services/ip_geolocation_service.md`

---

## 1) Purpose

`background_task_runner.py` is a **cross-domain runtime utility service** responsible for:
- registering background tasks,
- scheduling and repeatedly executing task loops,
- preventing duplicate/overlapping task execution,
- handling task lifecycle (start/stop/cancel),
- containing task exceptions and applying retry/backoff behavior.

It must remain **domain-agnostic** and reusable for current/future features (not just IP geolocation).

---

## 2) Layer Position and Boundaries

Expected flow:

`api -> apps -> services -> infra/models`

`background_task_runner` is part of `services`, but acts as a reusable runtime orchestration utility.

Boundary rules:
- Keep `background_task_runner` generic (looping, cancellation, interval scheduling, error boundaries).
- Keep domain refresh logic in domain-specific service modules (example: `ip_geolocation_data_refresher`).
- Do **not** place domain tasks under runner-specific directories like `background_task_runner/tasks/...`.

---

## 3) Planned Package Structure

```text
code/backend/services/
  background_task_runner/
    background_task_runner.py
    task_contracts.py              # optional protocols/interfaces
```

Potential companion modules (optional as complexity grows):
- `policies.py` (overlap/backoff policy enums)
- `task_state.py` (runtime state models)

---

## 4) Core Runtime Guarantees

`background_task_runner` should enforce these guarantees for every registered task:

1. **Single active task per `task_id`**
   - Keep a task registry keyed by `task_id`.
   - `start(task_id)` is idempotent: if already running, do not start a duplicate loop.

2. **No overlapping executions for the same task**
   - Guard each execution with a per-task run lock/flag.
   - Default overlap policy for polling tasks: `SKIP_IF_RUNNING` (best throughput, no queue buildup).
   - Optional policies for specific tasks: `QUEUE_ONE` or `RESTART`.

3. **Short critical sections only**
   - Locks in runner protect only registry/state transitions (start/stop/run markers), not task body work.
   - This avoids global coarse locks and keeps scheduling overhead low.

4. **Idempotent stop + graceful cancellation**
   - `stop(task_id)` can be called multiple times safely.
   - Cancellation boundaries should prevent zombie loops and double-stop races.

5. **Error boundary and backoff policy**
   - Task exceptions are contained per task.
   - Retry with bounded backoff/jitter to avoid hot error loops and contention spikes.

---

## 5) Task Contracts

Recommended contract shape for registered tasks:

- `task_id: str` (unique key)
- `interval_seconds: float`
- `run_once() -> None | Awaitable[None]`
- `overlap_policy` (default `SKIP_IF_RUNNING`)
- Optional retry/backoff config (base delay, max delay, jitter)

Registration behavior:
- `register(task)` should fail fast on duplicate `task_id` unless explicitly configured for replacement.
- `unregister(task_id)` should stop task first (if running), then remove from registry.

---

## 6) Lifecycle Interface (Planned)

Method naming examples:
- `start_background_task_runner()`
- `stop_background_task_runner()`
- `register_background_task(task)`
- `start_background_task(task_id)`
- `stop_background_task(task_id)`
- `get_background_task_status(task_id)`

Behavioral expectations:
- runner-level `start`/`stop` should be idempotent,
- task-level `start`/`stop` should be idempotent,
- stopping runner should safely stop/cancel all running tasks.

---

## 7) Observability and Health Signals

Expose at least task-level runtime metadata:
- `task_id`
- running/not-running state
- last run start timestamp
- last run success timestamp
- last error message (if any)
- consecutive failure count

Optional metrics:
- total runs
- skipped runs due to overlap
- average run duration
- retry/backoff counters

---

## 8) Integration Pattern (IP Geolocation Example)

For geolocation source watch/reload:

1. `ip_geolocation_data_refresher` defines domain logic:
   - source fingerprint check (`inode + mtime_ns`),
   - debounce and reload decision,
   - snapshot rebuild + atomic swap.

2. `background_task_runner` hosts lifecycle and scheduling:
   - starts/stops refresher polling loop,
   - enforces no-overlap policy,
   - handles exceptions/retries.

This keeps domain correctness and platform runtime responsibilities cleanly separated.

---

## 9) FastAPI Wiring and Automatic Server Startup

The intended runtime model is **in-process background execution bound to FastAPI app lifecycle**.
This means the runner starts when the backend app starts, and stops when the app stops.

### 9.1 Startup/shutdown flow with current `main.py`

Current server boot path in `code/backend/main.py` is:
- `uvicorn.run("main:create_app", factory=True, ...)`

With this pattern, the intended wiring is:

1. Uvicorn calls `create_app(...)`.
2. `create_app(...)` returns `FastAPI(..., lifespan=...)`.
3. In lifespan startup:
   - instantiate/get `background_task_runner`,
   - call `start_background_task_runner()`,
   - register domain task(s),
   - call `start_background_task(task_id)`.
4. App serves API traffic while task loops run in background.
5. In lifespan shutdown:
   - stop specific task(s) if needed,
   - call `stop_background_task_runner()` to cancel and cleanup gracefully.

### 9.2 Concrete wiring shape for `main.py`

Illustrative integration shape (kept generic, aligned to current `create_app` factory usage):

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI


@asynccontextmanager
async def _app_lifespan(app: FastAPI):
    # Resolve/create singleton runner instance for this process.
    runner = get_background_task_runner()

    # Example domain task creation (e.g. IP geolocation source watch).
    geo_refresh_task = build_ip_geolocation_refresh_task()

    runner.start_background_task_runner()
    runner.register_background_task(geo_refresh_task)
    runner.start_background_task(geo_refresh_task.task_id)

    try:
        yield
    finally:
        # Idempotent stop calls are expected by contract.
        runner.stop_background_task(geo_refresh_task.task_id)
        runner.stop_background_task_runner()


def create_app(frontend_mode: str | None = None, frontend_dev_url: str | None = None) -> FastAPI:
    app = FastAPI(
        title="BGPX Backend",
        version="0.1.0",
        lifespan=_app_lifespan,
    )
    # existing router/static wiring continues here
    return app
```

Notes:
- This design does **not** require a separate OS service/daemon for the runner.
- The runner is a managed background subsystem of the FastAPI process.

### 9.3 Reload and process model considerations (`reload=True`)

Your current `main.py` runs Uvicorn with `reload=True`.
Design expectations under reload:

- On code change, old process receives shutdown -> lifespan cleanup should stop tasks/runner.
- New process starts -> lifespan startup should start runner/tasks again.
- Runner/task APIs must remain idempotent (`start`/`stop`) to handle restarts safely.

If multi-worker mode is introduced in future, each worker process would run its own in-process runner
unless explicitly coordinated. For singleton global tasks, add cross-process coordination policy.

---

## 10) Minimal Integration Checklist

1. Implement `background_task_runner` module and lifecycle APIs from section 6.
2. Implement domain task factory (example: IP geolocation refresher task contract).
3. Add FastAPI lifespan function in `main.py`.
4. Start runner + register/start tasks in lifespan startup.
5. Stop tasks + runner in lifespan shutdown.
6. Verify behavior with `reload=True` (no duplicate loops after restart).
7. Add integration tests for startup/shutdown/background loop continuity.

---

## 11) Testing Plan

Unit tests:
- idempotent start/stop behavior
- no duplicate task loops for same `task_id`
- overlap behavior for each policy (`SKIP_IF_RUNNING` at minimum)
- cancellation and shutdown behavior
- exception containment and retry/backoff behavior
- registry consistency under start/stop/register/unregister races

Integration tests:
- runner + geolocation refresher collaboration
- file-change poll task continues after transient failures
- no double execution under rapid trigger conditions

---

## 12) Summary

This dedicated runner plan keeps:
- reusable background task mechanics centralized,
- domain services focused on business/data correctness,
- future background features easy to plug in without redesign.
