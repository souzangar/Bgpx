"""Background task runner core state machine primitives.

This module currently focuses on Step 3-5 of the implementation plan:
- task registry keyed by ``task_id``,
- per-task runtime state ownership,
- synchronization primitives with short critical sections.

Retry/backoff error policy execution flow is implemented in Step 6.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import UTC, datetime
import inspect
import logging
import os
import random
from threading import RLock
import time

from models.background_task_runner import BackgroundTaskDefinition, BackgroundTaskStatus


_VERBOSE_ENV = "BGPX_VERBOSE"
_TRUTHY_VALUES = {"1", "true", "yes", "on"}
_logger = logging.getLogger("uvicorn.error")

_IP_GEO_TASK_IDS = {
    "ip_geolocation_bootstrap_once",
    "ip_geolocation_ipinfo_gz_downloader",
    "ip_geolocation_data_refresh",
}


def _is_verbose_enabled() -> bool:
    """Return whether verbose logging is enabled from runtime environment."""
    return os.getenv(_VERBOSE_ENV, "0").strip().lower() in _TRUTHY_VALUES


@dataclass
class _RegisteredTaskState:
    """Internal runtime state for one registered background task."""

    task_definition: BackgroundTaskDefinition
    status: BackgroundTaskStatus
    run_in_progress: bool = False
    loop_handle: asyncio.Task[None] | None = None
    run_handle: asyncio.Task[None] | None = None
    next_eligible_run_at_monotonic: float = 0.0


@dataclass
class _ResourceGroupState:
    """Internal runtime state shared by tasks within the same resource key."""

    resource_key: str
    task_ids: list[str]
    active_task_id: str | None = None


class BackgroundTaskRunner:
    """Own process-local runtime state for background tasks.

    This class provides state ownership and lifecycle API idempotency guarantees.
    Scheduling loops and overlap execution flow are introduced in Step 5.
    """

    def __init__(self) -> None:
        self._registry: dict[str, _RegisteredTaskState] = {}
        self._resource_groups: dict[str, _ResourceGroupState] = {}
        self._runner_started: bool = False
        self._state_lock = RLock()
        self._sync_executor: ThreadPoolExecutor | None = None

    def _sort_resource_group_task_ids(self, task_ids: list[str]) -> list[str]:
        """Return task ids sorted by sequence, then task_id for stable ordering."""
        return sorted(
            task_ids,
            key=lambda task_id: (
                self._registry[task_id].task_definition.resource_sequence,
                task_id,
            ),
        )

    def _add_task_to_resource_group(self, task_definition: BackgroundTaskDefinition) -> None:
        """Register task membership in a resource group when key is provided."""
        resource_key = task_definition.resource_key
        if resource_key is None:
            return

        group_state = self._resource_groups.get(resource_key)
        if group_state is None:
            self._resource_groups[resource_key] = _ResourceGroupState(
                resource_key=resource_key,
                task_ids=[task_definition.task_id],
            )
            return

        group_state.task_ids.append(task_definition.task_id)
        group_state.task_ids = self._sort_resource_group_task_ids(group_state.task_ids)

    def _remove_task_from_resource_group(self, task_definition: BackgroundTaskDefinition) -> None:
        """Unregister task membership in a resource group when key is provided."""
        resource_key = task_definition.resource_key
        if resource_key is None:
            return

        group_state = self._resource_groups.get(resource_key)
        if group_state is None:
            return

        if task_definition.task_id in group_state.task_ids:
            group_state.task_ids.remove(task_definition.task_id)

        if group_state.active_task_id == task_definition.task_id:
            group_state.active_task_id = None

        if not group_state.task_ids:
            self._resource_groups.pop(resource_key, None)
            return

        group_state.task_ids = self._sort_resource_group_task_ids(group_state.task_ids)

    def _build_initial_task_status(self, task_id: str) -> BackgroundTaskStatus:
        """Create deterministic initial status for a newly registered task."""
        return BackgroundTaskStatus(task_id=task_id)

    def _require_registered_task(self, task_id: str) -> _RegisteredTaskState:
        """Return registered state or raise when task does not exist."""
        state = self._registry.get(task_id)
        if state is None:
            raise KeyError(f"Task '{task_id}' is not registered")
        return state

    def _is_registered(self, task_id: str) -> bool:
        """Return whether task is currently present in the registry."""
        with self._state_lock:
            return task_id in self._registry

    def _register_task_state(self, task_definition: BackgroundTaskDefinition) -> None:
        """Register a task in state registry.

        Raises:
            ValueError: if ``task_id`` is already registered.
        """
        with self._state_lock:
            if task_definition.task_id in self._registry:
                raise ValueError(f"Task '{task_definition.task_id}' is already registered")

            self._registry[task_definition.task_id] = _RegisteredTaskState(
                task_definition=task_definition,
                status=self._build_initial_task_status(task_definition.task_id),
            )
            self._add_task_to_resource_group(task_definition)

    def _unregister_task_state(self, task_id: str) -> _RegisteredTaskState:
        """Remove and return a task state from registry.

        Raises:
            KeyError: if ``task_id`` is not registered.
        """
        with self._state_lock:
            self._require_registered_task(task_id)
            removed_state = self._registry.pop(task_id)
            self._remove_task_from_resource_group(removed_state.task_definition)
            return removed_state

    def _resource_group_preceding_task_is_eligible(
        self,
        resource_group: _ResourceGroupState,
        task_id: str,
    ) -> bool:
        """Return whether earlier-sequence startup ordering should block this task.

        Sequence ordering is intended to guarantee deterministic *first-run* priority
        for lower-sequence tasks in the same resource group.

        After a preceding task has completed at least one run, it should no longer
        permanently gate higher-sequence periodic tasks, otherwise starvation can
        occur when the lower-sequence task remains continuously eligible.
        """
        try:
            current_index = resource_group.task_ids.index(task_id)
        except ValueError:
            return False

        for preceding_task_id in resource_group.task_ids[:current_index]:
            preceding_state = self._registry.get(preceding_task_id)
            if preceding_state is None:
                continue
            if not preceding_state.status.is_running:
                continue
            if preceding_state.status.total_runs > 0:
                continue
            if preceding_state.run_in_progress:
                continue
            if time.monotonic() < preceding_state.next_eligible_run_at_monotonic:
                continue
            return True

        return False

    def _get_task_status_snapshot(self, task_id: str) -> BackgroundTaskStatus:
        """Return a copy of task status for safe external reads."""
        with self._state_lock:
            state = self._require_registered_task(task_id)
            return replace(state.status)

    def _set_task_status(self, task_id: str, status: BackgroundTaskStatus) -> None:
        """Replace current task status after basic consistency validation."""
        if status.task_id != task_id:
            raise ValueError("status.task_id must match target task_id")

        with self._state_lock:
            state = self._require_registered_task(task_id)
            state.status = status

    def _list_registered_task_ids(self) -> tuple[str, ...]:
        """Return immutable snapshot of currently registered task ids."""
        with self._state_lock:
            return tuple(self._registry.keys())

    def _compute_backoff_delay_seconds(
        self,
        task_definition: BackgroundTaskDefinition,
        consecutive_failure_count: int,
    ) -> float:
        """Compute bounded exponential backoff delay with optional jitter."""
        retry_config = task_definition.retry_backoff
        exponential_delay = retry_config.base_delay_seconds * (
            2 ** max(consecutive_failure_count - 1, 0)
        )
        bounded_delay = min(exponential_delay, retry_config.max_delay_seconds)

        jitter_delta = bounded_delay * retry_config.jitter_ratio
        if jitter_delta > 0:
            bounded_delay += random.uniform(-jitter_delta, jitter_delta)

        return max(0.0, min(bounded_delay, retry_config.max_delay_seconds))

    async def _run_registered_task_loop(self, task_id: str) -> None:
        """Run scheduling loop for one registered task id until stopped/cancelled."""
        try:
            while True:
                with self._state_lock:
                    state = self._registry.get(task_id)
                    if state is None:
                        return

                    if not self._runner_started or not state.status.is_running:
                        return

                    interval_seconds = state.task_definition.interval_seconds

                self._schedule_task_run_if_possible(task_id)
                await asyncio.sleep(interval_seconds)
        finally:
            with self._state_lock:
                state = self._registry.get(task_id)
                if state is not None:
                    current_task = asyncio.current_task()
                    if state.loop_handle is current_task:
                        state.loop_handle = None

    def _is_task_eligible_for_scheduling(self, state: _RegisteredTaskState) -> bool:
        """Return whether baseline lifecycle/backoff checks allow scheduling."""
        if not self._runner_started or not state.status.is_running:
            return False

        if time.monotonic() < state.next_eligible_run_at_monotonic:
            return False

        return True

    def _is_resource_group_blocking_run(self, task_id: str, state: _RegisteredTaskState) -> bool:
        """Return whether resource-group constraints currently block this run."""
        resource_key = state.task_definition.resource_key
        if resource_key is None:
            return False

        resource_group = self._resource_groups.get(resource_key)
        if resource_group is None:
            return False

        if resource_group.active_task_id is not None and resource_group.active_task_id != task_id:
            state.status = replace(
                state.status,
                skipped_overlap_runs=state.status.skipped_overlap_runs + 1,
            )
            if _is_verbose_enabled() and task_id in _IP_GEO_TASK_IDS:
                _logger.info(
                    "BG runner skip task_id=%s reason=resource_group_active active_task_id=%s",
                    task_id,
                    resource_group.active_task_id,
                )
            return True

        if self._resource_group_preceding_task_is_eligible(resource_group, task_id):
            if _is_verbose_enabled() and task_id in _IP_GEO_TASK_IDS:
                _logger.info(
                    "BG runner skip task_id=%s reason=preceding_task_eligible",
                    task_id,
                )
            return True

        return False

    def _set_task_as_running_for_next_run(self, task_id: str, state: _RegisteredTaskState) -> None:
        """Mark task state as running for a newly scheduled run."""
        state.run_in_progress = True
        resource_key = state.task_definition.resource_key
        if resource_key is not None:
            resource_group = self._resource_groups.get(resource_key)
            if resource_group is not None:
                resource_group.active_task_id = task_id

        state.status = replace(
            state.status,
            last_run_started_at=datetime.now(UTC),
            total_runs=state.status.total_runs + 1,
        )

    def _schedule_task_run_if_possible(self, task_id: str) -> None:
        """Schedule one task run while enforcing overlap policy."""
        should_spawn_run_task = False

        with self._state_lock:
            state = self._registry.get(task_id)
            if state is None:
                return

            if not self._is_task_eligible_for_scheduling(state):
                return

            if self._is_resource_group_blocking_run(task_id, state):
                return

            if state.run_in_progress:
                # Step 5 fully implements SKIP_IF_RUNNING. Other policies remain
                # future-ready placeholders and currently use safe skip behavior.
                state.status = replace(
                    state.status,
                    skipped_overlap_runs=state.status.skipped_overlap_runs + 1,
                )
                if _is_verbose_enabled() and task_id in _IP_GEO_TASK_IDS:
                    _logger.info(
                        "BG runner skip task_id=%s reason=run_in_progress",
                        task_id,
                    )
                return

            self._set_task_as_running_for_next_run(task_id, state)
            should_spawn_run_task = True

        if not should_spawn_run_task:
            return

        if _is_verbose_enabled() and task_id in _IP_GEO_TASK_IDS:
            _logger.info("BG runner schedule task_id=%s", task_id)

        run_task = asyncio.create_task(
            self._execute_registered_task_run(task_id),
            name=f"background-task-run:{task_id}",
        )

        with self._state_lock:
            state = self._registry.get(task_id)
            if state is None or not state.run_in_progress:
                run_task.cancel()
                return
            state.run_handle = run_task

    async def _execute_registered_task_run(self, task_id: str) -> None:
        """Execute one task run and release per-task running guard."""
        run_callable = self._get_registered_run_callable(task_id)
        if run_callable is None:
            return

        succeeded = False
        error_message: str | None = None
        was_cancelled = False

        try:
            await self._invoke_registered_run_callable(run_callable)
            succeeded = True
        except asyncio.CancelledError:
            was_cancelled = True
            raise
        except Exception as exc:  # pragma: no cover - step 6 will formalize policy
            error_message = str(exc) or exc.__class__.__name__
        finally:
            self._finalize_registered_task_run(
                task_id=task_id,
                succeeded=succeeded,
                error_message=error_message,
                was_cancelled=was_cancelled,
            )

    def _get_registered_run_callable(self, task_id: str):
        """Return run callable for registered task, or ``None`` if task disappeared."""
        with self._state_lock:
            state = self._registry.get(task_id)
            if state is None:
                return None
            return state.task_definition.run_once

    async def _invoke_registered_run_callable(self, run_callable) -> None:
        """Invoke task callable using async path or executor for sync callables."""
        if inspect.iscoroutinefunction(run_callable):
            await run_callable()
            return

        event_loop = asyncio.get_running_loop()
        with self._state_lock:
            sync_executor = self._sync_executor
        await event_loop.run_in_executor(sync_executor, run_callable)

    def _release_runtime_guards_after_run(
        self,
        task_id: str,
        state: _RegisteredTaskState,
    ) -> None:
        """Release run/resource guard markers once a run attempt finishes."""
        if state.run_handle is asyncio.current_task():
            state.run_handle = None

        state.run_in_progress = False
        resource_key = state.task_definition.resource_key
        if resource_key is None:
            return

        resource_group = self._resource_groups.get(resource_key)
        if resource_group is not None and resource_group.active_task_id == task_id:
            resource_group.active_task_id = None

    def _apply_success_status_after_run(self, state: _RegisteredTaskState) -> None:
        """Apply status mutations for successful run completion."""
        state.status = replace(
            state.status,
            last_run_succeeded_at=datetime.now(UTC),
            last_error_message=None,
            consecutive_failure_count=0,
        )
        state.next_eligible_run_at_monotonic = 0.0

    def _stop_task_loop_after_success(
        self,
        state: _RegisteredTaskState,
        tasks_to_cancel: list[asyncio.Task[None]],
    ) -> None:
        """Stop one-shot task loop after a successful run without cancelling current run."""
        if not state.task_definition.stop_after_success:
            return

        state.status = replace(state.status, is_running=False)
        if state.loop_handle is not None:
            tasks_to_cancel.append(state.loop_handle)
            state.loop_handle = None

    def _apply_failure_status_after_run(
        self,
        state: _RegisteredTaskState,
        error_message: str,
    ) -> None:
        """Apply status mutations/backoff for failed run completion."""
        next_failure_count = state.status.consecutive_failure_count + 1
        backoff_delay_seconds = self._compute_backoff_delay_seconds(
            state.task_definition,
            next_failure_count,
        )
        state.next_eligible_run_at_monotonic = time.monotonic() + backoff_delay_seconds
        state.status = replace(
            state.status,
            last_error_message=error_message,
            consecutive_failure_count=next_failure_count,
        )

    def _reset_task_runtime_markers_on_runner_stop(
        self,
        state: _RegisteredTaskState,
        tasks_to_cancel: list[asyncio.Task[None]],
    ) -> None:
        """Reset one task runtime markers and collect handles to cancel."""
        state.run_in_progress = False
        state.next_eligible_run_at_monotonic = 0.0

        resource_key = state.task_definition.resource_key
        if resource_key is not None:
            resource_group = self._resource_groups.get(resource_key)
            if resource_group is not None:
                resource_group.active_task_id = None

        if state.loop_handle is not None:
            tasks_to_cancel.append(state.loop_handle)
            state.loop_handle = None

        if state.run_handle is not None:
            tasks_to_cancel.append(state.run_handle)
            state.run_handle = None

        if state.status.is_running:
            state.status = replace(state.status, is_running=False)

    def _collect_peer_task_ids_for_scheduling(
        self,
        task_id: str,
        state: _RegisteredTaskState,
    ) -> list[str]:
        """Return peer task ids in the same resource group eligible for immediate scheduling.

        Called under ``_state_lock`` after releasing runtime guards so that peers
        blocked by this task's ``active_task_id`` get an immediate scheduling
        opportunity rather than waiting for their next loop tick.
        """
        resource_key = state.task_definition.resource_key
        if resource_key is None:
            return []

        resource_group = self._resource_groups.get(resource_key)
        if resource_group is None:
            return []

        peer_ids: list[str] = []
        for peer_id in resource_group.task_ids:
            if peer_id == task_id:
                continue
            peer_state = self._registry.get(peer_id)
            if peer_state is None:
                continue
            if peer_state.status.is_running and not peer_state.run_in_progress:
                peer_ids.append(peer_id)

        return peer_ids

    def _finalize_registered_task_run(
        self,
        task_id: str,
        succeeded: bool,
        error_message: str | None,
        was_cancelled: bool,
    ) -> None:
        """Finalize run attempt by releasing guards and applying status policy."""
        tasks_to_cancel: list[asyncio.Task[None]] = []
        peer_task_ids_to_schedule: list[str] = []

        with self._state_lock:
            state = self._registry.get(task_id)
            if state is None:
                return

            self._release_runtime_guards_after_run(task_id, state)

            # Collect peers that may have been blocked by this task holding
            # the resource group active_task_id.  They get an immediate
            # scheduling attempt after the lock is released.
            peer_task_ids_to_schedule = self._collect_peer_task_ids_for_scheduling(
                task_id, state
            )

            if was_cancelled:
                # Still allow peer scheduling even on cancellation so the
                # resource group is not permanently starved.
                pass
            elif succeeded:
                self._apply_success_status_after_run(state)
                self._stop_task_loop_after_success(state, tasks_to_cancel)
            elif error_message is not None:
                self._apply_failure_status_after_run(state, error_message)

        current_task = asyncio.current_task()
        for task in tasks_to_cancel:
            if task is not current_task and not task.done():
                task.cancel()

        # Immediate peer scheduling — breaks phase-alignment starvation.
        for peer_id in peer_task_ids_to_schedule:
            if _is_verbose_enabled() and peer_id in _IP_GEO_TASK_IDS:
                _logger.info(
                    "BG runner peer-schedule task_id=%s triggered_by=%s",
                    peer_id,
                    task_id,
                )
            self._schedule_task_run_if_possible(peer_id)

    def start_background_task_runner(self) -> None:
        """Start runner lifecycle idempotently."""
        with self._state_lock:
            if self._runner_started:
                return

            if self._sync_executor is None:
                self._sync_executor = ThreadPoolExecutor(
                    max_workers=2,
                    thread_name_prefix="bg-task-runner",
                )
            self._runner_started = True

    def stop_background_task_runner(self) -> None:
        """Stop runner lifecycle idempotently and clear task runtime markers."""
        tasks_to_cancel: list[asyncio.Task[None]] = []
        executor_to_shutdown: ThreadPoolExecutor | None = None

        with self._state_lock:
            if not self._runner_started:
                return

            self._runner_started = False
            executor_to_shutdown = self._sync_executor
            self._sync_executor = None

            for state in self._registry.values():
                self._reset_task_runtime_markers_on_runner_stop(state, tasks_to_cancel)

        for task in tasks_to_cancel:
            if not task.done():
                task.cancel()

        if executor_to_shutdown is not None:
            executor_to_shutdown.shutdown(wait=False, cancel_futures=False)

    def register_background_task(self, task: BackgroundTaskDefinition) -> None:
        """Register task definition in runner registry.

        Raises:
            ValueError: if task_id already exists.
        """
        self._register_task_state(task)

    def unregister_background_task(self, task_id: str) -> None:
        """Unregister task definition after idempotent logical stop."""
        self.stop_background_task(task_id)
        self._unregister_task_state(task_id)

    def start_background_task(self, task_id: str) -> None:
        """Start one registered task idempotently.

        Raises:
            RuntimeError: if runner is not started.
            RuntimeError: if no active asyncio event loop is running.
            KeyError: if task_id is not registered.
        """
        try:
            event_loop = asyncio.get_running_loop()
        except RuntimeError as exc:
            raise RuntimeError(
                "start_background_task must be called inside an active asyncio event loop"
            ) from exc

        with self._state_lock:
            if not self._runner_started:
                raise RuntimeError("Background task runner is not started")

            state = self._require_registered_task(task_id)
            if state.status.is_running and state.loop_handle is not None and not state.loop_handle.done():
                return

            state.status = replace(state.status, is_running=True)
            state.run_in_progress = False
            state.next_eligible_run_at_monotonic = 0.0
            state.loop_handle = event_loop.create_task(
                self._run_registered_task_loop(task_id),
                name=f"background-task-loop:{task_id}",
            )

    def stop_background_task(self, task_id: str) -> None:
        """Stop one registered task idempotently.

        Raises:
            KeyError: if task_id is not registered.
        """
        tasks_to_cancel: list[asyncio.Task[None]] = []

        with self._state_lock:
            state = self._require_registered_task(task_id)
            if (
                not state.status.is_running
                and not state.run_in_progress
                and state.loop_handle is None
                and state.run_handle is None
            ):
                return

            state.status = replace(state.status, is_running=False)
            state.run_in_progress = False
            state.next_eligible_run_at_monotonic = 0.0
            resource_key = state.task_definition.resource_key
            if resource_key is not None:
                resource_group = self._resource_groups.get(resource_key)
                if resource_group is not None and resource_group.active_task_id == task_id:
                    resource_group.active_task_id = None
            if state.loop_handle is not None:
                tasks_to_cancel.append(state.loop_handle)
            state.loop_handle = None

            if state.run_handle is not None:
                tasks_to_cancel.append(state.run_handle)
            state.run_handle = None

        for task in tasks_to_cancel:
            if not task.done():
                task.cancel()

    def get_background_task_status(self, task_id: str) -> BackgroundTaskStatus:
        """Return a safe snapshot of current task runtime status."""
        return self._get_task_status_snapshot(task_id)


_process_local_runner: BackgroundTaskRunner | None = None
_process_local_runner_lock = RLock()


def get_background_task_runner() -> BackgroundTaskRunner:
    """Return process-local shared runner instance.

    The accessor lazily creates exactly one runner instance per backend process.
    This is intended for app-lifecycle wiring (e.g., FastAPI lifespan startup/
    shutdown) where background tasks should share a single runtime owner.
    """

    global _process_local_runner

    with _process_local_runner_lock:
        if _process_local_runner is None:
            _process_local_runner = BackgroundTaskRunner()
        return _process_local_runner


def reset_background_task_runner_for_tests() -> None:
    """Reset process-local runner singleton for test isolation.

    If a shared runner exists, it is stopped first to ensure pending task loop/
    run handles are cancelled before clearing the accessor state.
    """

    global _process_local_runner

    with _process_local_runner_lock:
        if _process_local_runner is not None:
            _process_local_runner.stop_background_task_runner()
        _process_local_runner = None


__all__ = [
    "BackgroundTaskRunner",
    "get_background_task_runner",
    "reset_background_task_runner_for_tests",
]
