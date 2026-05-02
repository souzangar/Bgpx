"""Background task runner core state machine primitives.

This module currently focuses on Step 3-5 of the implementation plan:
- task registry keyed by ``task_id``,
- per-task runtime state ownership,
- synchronization primitives with short critical sections.

Retry/backoff error policy execution flow is implemented in Step 6.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import UTC, datetime
import inspect
import random
from threading import RLock
import time

from models.background_task_runner import BackgroundTaskDefinition, BackgroundTaskStatus


@dataclass
class _RegisteredTaskState:
    """Internal runtime state for one registered background task."""

    task_definition: BackgroundTaskDefinition
    status: BackgroundTaskStatus
    run_in_progress: bool = False
    loop_handle: asyncio.Task[None] | None = None
    run_handle: asyncio.Task[None] | None = None
    next_eligible_run_at_monotonic: float = 0.0


class BackgroundTaskRunner:
    """Own process-local runtime state for background tasks.

    This class provides state ownership and lifecycle API idempotency guarantees.
    Scheduling loops and overlap execution flow are introduced in Step 5.
    """

    def __init__(self) -> None:
        self._registry: dict[str, _RegisteredTaskState] = {}
        self._runner_started: bool = False
        self._state_lock = RLock()

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

    def _unregister_task_state(self, task_id: str) -> _RegisteredTaskState:
        """Remove and return a task state from registry.

        Raises:
            KeyError: if ``task_id`` is not registered.
        """
        with self._state_lock:
            self._require_registered_task(task_id)
            return self._registry.pop(task_id)

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

                await self._schedule_task_run_if_possible(task_id)
                await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            raise
        finally:
            with self._state_lock:
                state = self._registry.get(task_id)
                if state is None:
                    return

                current_task = asyncio.current_task()
                if state.loop_handle is current_task:
                    state.loop_handle = None

    async def _schedule_task_run_if_possible(self, task_id: str) -> None:
        """Schedule one task run while enforcing overlap policy."""
        with self._state_lock:
            state = self._registry.get(task_id)
            if state is None:
                return

            if not self._runner_started or not state.status.is_running:
                return

            if time.monotonic() < state.next_eligible_run_at_monotonic:
                return

            if state.run_in_progress:
                # Step 5 fully implements SKIP_IF_RUNNING. Other policies remain
                # future-ready placeholders and currently use safe skip behavior.
                state.status = replace(
                    state.status,
                    skipped_overlap_runs=state.status.skipped_overlap_runs + 1,
                )
                return

            state.run_in_progress = True
            state.status = replace(
                state.status,
                last_run_started_at=datetime.now(UTC),
                total_runs=state.status.total_runs + 1,
            )

            run_task = asyncio.create_task(
                self._execute_registered_task_run(task_id),
                name=f"background-task-run:{task_id}",
            )
            state.run_handle = run_task

    async def _execute_registered_task_run(self, task_id: str) -> None:
        """Execute one task run and release per-task running guard."""
        run_callable = None

        with self._state_lock:
            state = self._registry.get(task_id)
            if state is None:
                return
            run_callable = state.task_definition.run_once

        succeeded = False
        error_message: str | None = None
        was_cancelled = False

        try:
            result = run_callable()
            if inspect.isawaitable(result):
                await result
            succeeded = True
        except asyncio.CancelledError:
            was_cancelled = True
            raise
        except Exception as exc:  # pragma: no cover - step 6 will formalize policy
            error_message = str(exc) or exc.__class__.__name__
        finally:
            with self._state_lock:
                state = self._registry.get(task_id)
                if state is None:
                    return

                if state.run_handle is asyncio.current_task():
                    state.run_handle = None

                state.run_in_progress = False

                if was_cancelled:
                    return

                if succeeded:
                    state.status = replace(
                        state.status,
                        last_run_succeeded_at=datetime.now(UTC),
                        last_error_message=None,
                        consecutive_failure_count=0,
                    )
                    state.next_eligible_run_at_monotonic = 0.0
                elif error_message is not None:
                    next_failure_count = state.status.consecutive_failure_count + 1
                    backoff_delay_seconds = self._compute_backoff_delay_seconds(
                        state.task_definition,
                        next_failure_count,
                    )
                    state.next_eligible_run_at_monotonic = (
                        time.monotonic() + backoff_delay_seconds
                    )
                    state.status = replace(
                        state.status,
                        last_error_message=error_message,
                        consecutive_failure_count=next_failure_count,
                    )

    def start_background_task_runner(self) -> None:
        """Start runner lifecycle idempotently."""
        with self._state_lock:
            if self._runner_started:
                return

            self._runner_started = True

    def stop_background_task_runner(self) -> None:
        """Stop runner lifecycle idempotently and clear task runtime markers."""
        tasks_to_cancel: list[asyncio.Task[None]] = []

        with self._state_lock:
            if not self._runner_started:
                return

            self._runner_started = False

            for state in self._registry.values():
                state.run_in_progress = False
                state.next_eligible_run_at_monotonic = 0.0
                if state.loop_handle is not None:
                    tasks_to_cancel.append(state.loop_handle)
                    state.loop_handle = None

                if state.run_handle is not None:
                    tasks_to_cancel.append(state.run_handle)
                    state.run_handle = None

                if state.status.is_running:
                    state.status = replace(state.status, is_running=False)

        for task in tasks_to_cancel:
            if not task.done():
                task.cancel()

    def register_background_task(self, task: BackgroundTaskDefinition) -> None:
        """Register task definition in runner registry.

        Raises:
            ValueError: if task_id already exists.
        """
        self._register_task_state(task)

    def unregister_background_task(self, task_id: str) -> None:
        """Unregister task definition after idempotent logical stop."""
        self.stop_background_task(task_id)

        with self._state_lock:
            self._require_registered_task(task_id)
            self._registry.pop(task_id)

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
