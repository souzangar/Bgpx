"""Unit tests for background task runner runtime behavior."""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys

import pytest


BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.background_task_runner import (  # noqa: E402
    BackgroundTaskDefinition,
    BackgroundTaskRunner,
    RetryBackoffConfig,
    get_background_task_runner,
    reset_background_task_runner_for_tests,
)


def _build_task(
    task_id: str,
    run_once,
    *,
    interval_seconds: float = 0.01,
    base_delay_seconds: float = 0.01,
    max_delay_seconds: float = 0.05,
    jitter_ratio: float = 0.0,
    resource_key: str | None = None,
    resource_sequence: int = 0,
    stop_after_success: bool = False,
) -> BackgroundTaskDefinition:
    """Create test task definition with deterministic retry config."""
    return BackgroundTaskDefinition(
        task_id=task_id,
        interval_seconds=interval_seconds,
        run_once=run_once,
        retry_backoff=RetryBackoffConfig(
            base_delay_seconds=base_delay_seconds,
            max_delay_seconds=max_delay_seconds,
            jitter_ratio=jitter_ratio,
        ),
        resource_key=resource_key,
        resource_sequence=resource_sequence,
        stop_after_success=stop_after_success,
    )


def test_runner_start_stop_are_idempotent() -> None:
    """Runner lifecycle start/stop should be safe to call repeatedly."""
    runner = BackgroundTaskRunner()

    runner.start_background_task_runner()
    runner.start_background_task_runner()
    assert runner._runner_started is True

    runner.stop_background_task_runner()
    runner.stop_background_task_runner()
    assert runner._runner_started is False


def test_register_duplicate_task_id_raises_value_error() -> None:
    """Registering the same task id more than once should fail fast."""
    runner = BackgroundTaskRunner()
    task = _build_task("dup-task", lambda: None)

    runner.register_background_task(task)

    with pytest.raises(ValueError, match="already registered"):
        runner.register_background_task(task)


def test_unregister_unknown_task_raises_key_error() -> None:
    """Unregistering a non-existent task should raise KeyError."""
    runner = BackgroundTaskRunner()

    with pytest.raises(KeyError, match="not registered"):
        runner.unregister_background_task("missing-task")


def test_start_background_task_requires_running_event_loop() -> None:
    """Starting a task outside active event loop should raise RuntimeError."""
    runner = BackgroundTaskRunner()
    runner.start_background_task_runner()
    runner.register_background_task(_build_task("loop-required", lambda: None))

    with pytest.raises(RuntimeError, match="active asyncio event loop"):
        runner.start_background_task("loop-required")


def test_start_background_task_requires_runner_started() -> None:
    """Task start should fail when runner lifecycle is not started."""

    async def _scenario() -> None:
        runner = BackgroundTaskRunner()
        runner.register_background_task(_build_task("runner-not-started", lambda: None))
        await asyncio.sleep(0)

        with pytest.raises(RuntimeError, match="not started"):
            runner.start_background_task("runner-not-started")

    asyncio.run(_scenario())


def test_peer_scheduling_prevents_resource_group_starvation():
    """Verify higher-sequence peer gets scheduled after lower-sequence task finishes.

    This reproduces the phase-alignment starvation bug where two tasks with the
    same interval in the same resource group can cause the higher-sequence task
    to never run because the lower-sequence task always re-claims active_task_id
    before the higher-sequence task's loop tick fires.

    The fix: after a task run finishes and releases the resource group, peers get
    an immediate scheduling opportunity via _collect_peer_task_ids_for_scheduling.
    """

    async def _scenario():
        runner = BackgroundTaskRunner()
        runner.start_background_task_runner()

        seq10_runs = []
        seq20_runs = []

        def _seq10_work():
            seq10_runs.append(1)

        def _seq20_work():
            seq20_runs.append(1)

        task_seq10 = _build_task(
            "downloader",
            _seq10_work,
            interval_seconds=0.05,
            resource_key="shared_resource",
            resource_sequence=10,
        )
        task_seq20 = _build_task(
            "refresher",
            _seq20_work,
            interval_seconds=0.05,
            resource_key="shared_resource",
            resource_sequence=20,
        )

        runner.register_background_task(task_seq10)
        runner.register_background_task(task_seq20)
        runner.start_background_task("downloader")
        runner.start_background_task("refresher")

        try:
            # Allow enough time for multiple cycles. Without the fix, refresher
            # would accumulate 0 runs while downloader runs many times.
            await asyncio.sleep(0.25)

            downloader_status = runner.get_background_task_status("downloader")
            refresher_status = runner.get_background_task_status("refresher")

            # Both should have run multiple times
            assert downloader_status.total_runs >= 2, (
                f"downloader total_runs={downloader_status.total_runs}, expected >= 2"
            )
            assert refresher_status.total_runs >= 2, (
                f"refresher total_runs={refresher_status.total_runs}, expected >= 2"
            )
            # Refresher should not be permanently starved
            assert len(seq20_runs) >= 2, (
                f"seq20 (refresher) ran {len(seq20_runs)} times, expected >= 2"
            )
        finally:
            runner.stop_background_task("downloader")
            runner.stop_background_task("refresher")
            runner.stop_background_task_runner()
            await asyncio.sleep(0.01)

    asyncio.run(_scenario())


def test_start_background_task_is_idempotent_and_keeps_single_loop_handle() -> None:
    """Second start call should not create duplicate task loop for same task id."""

    async def _scenario() -> None:
        runner = BackgroundTaskRunner()
        task_id = "idempotent-start"

        async def _run_once() -> None:
            await asyncio.sleep(0.02)

        runner.start_background_task_runner()
        runner.register_background_task(_build_task(task_id, _run_once, interval_seconds=0.01))
        runner.start_background_task(task_id)

        try:
            first_loop_handle = runner._registry[task_id].loop_handle
            runner.start_background_task(task_id)
            second_loop_handle = runner._registry[task_id].loop_handle

            assert first_loop_handle is not None
            assert second_loop_handle is first_loop_handle
        finally:
            runner.stop_background_task(task_id)
            runner.stop_background_task_runner()
            await asyncio.sleep(0.01)

    asyncio.run(_scenario())


def test_stop_background_task_is_idempotent() -> None:
    """Stopping an already-stopped task should not raise or regress state."""

    async def _scenario() -> None:
        runner = BackgroundTaskRunner()
        task_id = "idempotent-stop"
        runner.start_background_task_runner()
        runner.register_background_task(_build_task(task_id, lambda: None))
        runner.start_background_task(task_id)

        try:
            await asyncio.sleep(0.02)
            runner.stop_background_task(task_id)
            runner.stop_background_task(task_id)

            status = runner.get_background_task_status(task_id)
            assert status.is_running is False
        finally:
            runner.stop_background_task_runner()
            await asyncio.sleep(0.01)

    asyncio.run(_scenario())


def test_unregister_background_task_stops_and_removes_state() -> None:
    """Unregister should stop any running loop and remove task from registry."""

    async def _scenario() -> None:
        runner = BackgroundTaskRunner()
        task_id = "unregister-running"

        async def _run_once() -> None:
            await asyncio.sleep(0.03)

        runner.start_background_task_runner()
        runner.register_background_task(_build_task(task_id, _run_once, interval_seconds=0.01))
        runner.start_background_task(task_id)

        try:
            await asyncio.sleep(0.02)
            runner.unregister_background_task(task_id)

            with pytest.raises(KeyError, match="not registered"):
                runner.get_background_task_status(task_id)

            assert task_id not in runner._list_registered_task_ids()
        finally:
            runner.stop_background_task_runner()
            await asyncio.sleep(0.01)

    asyncio.run(_scenario())


def test_overlap_skip_if_running_increments_skipped_counter_without_concurrency() -> None:
    """Long task body + short interval should trigger SKIP_IF_RUNNING accounting."""

    async def _scenario() -> None:
        runner = BackgroundTaskRunner()
        task_id = "overlap-skip"
        active_runs = 0
        max_concurrent_runs = 0

        async def _run_once() -> None:
            nonlocal active_runs, max_concurrent_runs
            active_runs += 1
            max_concurrent_runs = max(max_concurrent_runs, active_runs)
            try:
                await asyncio.sleep(0.04)
            finally:
                active_runs -= 1

        runner.start_background_task_runner()
        runner.register_background_task(_build_task(task_id, _run_once, interval_seconds=0.01))
        runner.start_background_task(task_id)

        try:
            await asyncio.sleep(0.14)
            status = runner.get_background_task_status(task_id)

            assert status.total_runs >= 1
            assert status.skipped_overlap_runs > 0
            assert max_concurrent_runs == 1
        finally:
            runner.stop_background_task(task_id)
            runner.stop_background_task_runner()
            await asyncio.sleep(0.01)

    asyncio.run(_scenario())


def test_stop_background_task_runner_cancels_handles_and_marks_task_stopped() -> None:
    """Runner stop should clear active loop/run handles and task running state."""

    async def _scenario() -> None:
        runner = BackgroundTaskRunner()
        task_id = "runner-stop-cancel"
        task_started = asyncio.Event()

        async def _run_once() -> None:
            task_started.set()
            await asyncio.sleep(0.5)

        runner.start_background_task_runner()
        runner.register_background_task(_build_task(task_id, _run_once, interval_seconds=0.01))
        runner.start_background_task(task_id)

        try:
            await asyncio.wait_for(task_started.wait(), timeout=0.2)
            runner.stop_background_task_runner()
            await asyncio.sleep(0.02)

            status = runner.get_background_task_status(task_id)
            state = runner._registry[task_id]

            assert status.is_running is False
            assert state.loop_handle is None
            assert state.run_handle is None
            assert state.run_in_progress is False
        finally:
            runner.stop_background_task_runner()
            await asyncio.sleep(0.01)

    asyncio.run(_scenario())


def test_task_failure_updates_status_and_honors_backoff_window() -> None:
    """Failure should update status and delay immediate retrigger via backoff."""

    async def _scenario() -> None:
        runner = BackgroundTaskRunner()
        task_id = "failure-backoff"

        def _run_once() -> None:
            raise RuntimeError("boom")

        runner.start_background_task_runner()
        runner.register_background_task(
            _build_task(
                task_id,
                _run_once,
                interval_seconds=0.01,
                base_delay_seconds=0.05,
                max_delay_seconds=0.05,
                jitter_ratio=0.0,
            )
        )
        runner.start_background_task(task_id)

        try:
            await asyncio.sleep(0.025)
            early_status = runner.get_background_task_status(task_id)

            assert early_status.total_runs == 1
            assert early_status.last_error_message == "boom"
            assert early_status.consecutive_failure_count >= 1

            await asyncio.sleep(0.07)
            later_status = runner.get_background_task_status(task_id)
            assert later_status.total_runs >= 2
        finally:
            runner.stop_background_task(task_id)
            runner.stop_background_task_runner()
            await asyncio.sleep(0.01)

    asyncio.run(_scenario())


def test_success_after_failure_resets_failure_state() -> None:
    """A successful later run should clear consecutive failure/error status."""

    async def _scenario() -> None:
        runner = BackgroundTaskRunner()
        task_id = "fail-then-success"
        attempt_count = 0

        def _run_once() -> None:
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count == 1:
                raise RuntimeError("fail-once")

        runner.start_background_task_runner()
        runner.register_background_task(
            _build_task(
                task_id,
                _run_once,
                interval_seconds=0.01,
                base_delay_seconds=0.01,
                max_delay_seconds=0.01,
                jitter_ratio=0.0,
            )
        )
        runner.start_background_task(task_id)

        try:
            await asyncio.sleep(0.08)
            status = runner.get_background_task_status(task_id)

            assert attempt_count >= 2
            assert status.total_runs >= 2
            assert status.consecutive_failure_count == 0
            assert status.last_error_message is None
            assert status.last_run_succeeded_at is not None
        finally:
            runner.stop_background_task(task_id)
            runner.stop_background_task_runner()
            await asyncio.sleep(0.01)

    asyncio.run(_scenario())


def test_process_local_singleton_accessor_and_reset_behavior() -> None:
    """Accessor should return one shared instance until reset is invoked."""
    reset_background_task_runner_for_tests()

    try:
        first = get_background_task_runner()
        second = get_background_task_runner()
        assert first is second

        reset_background_task_runner_for_tests()
        third = get_background_task_runner()
        assert third is not first
    finally:
        reset_background_task_runner_for_tests()


def test_sync_task_run_is_offloaded_and_keeps_event_loop_responsive() -> None:
    """Sync run_once should execute without blocking unrelated event-loop progress."""

    async def _scenario() -> None:
        runner = BackgroundTaskRunner()
        task_id = "sync-offload"

        def _run_once() -> None:
            import time

            time.sleep(0.05)

        runner.start_background_task_runner()
        runner.register_background_task(_build_task(task_id, _run_once, interval_seconds=0.2))
        runner.start_background_task(task_id)

        ticker_count = 0

        async def _ticker() -> None:
            nonlocal ticker_count
            for _ in range(6):
                await asyncio.sleep(0.01)
                ticker_count += 1

        try:
            await _ticker()
            assert ticker_count == 6
        finally:
            runner.stop_background_task(task_id)
            runner.stop_background_task_runner()
            await asyncio.sleep(0.01)

    asyncio.run(_scenario())


def test_resource_key_group_prevents_overlap_between_distinct_tasks() -> None:
    """Tasks sharing one resource_key should never execute concurrently."""

    async def _scenario() -> None:
        runner = BackgroundTaskRunner()
        active_runs = 0
        max_concurrent_runs = 0

        async def _run_once() -> None:
            nonlocal active_runs, max_concurrent_runs
            active_runs += 1
            max_concurrent_runs = max(max_concurrent_runs, active_runs)
            try:
                await asyncio.sleep(0.03)
            finally:
                active_runs -= 1

        runner.start_background_task_runner()
        runner.register_background_task(
            _build_task(
                "group-a",
                _run_once,
                interval_seconds=0.01,
                resource_key="shared-resource",
                resource_sequence=10,
            )
        )
        runner.register_background_task(
            _build_task(
                "group-b",
                _run_once,
                interval_seconds=0.01,
                resource_key="shared-resource",
                resource_sequence=20,
            )
        )
        runner.start_background_task("group-a")
        runner.start_background_task("group-b")

        try:
            await asyncio.sleep(0.18)
            assert max_concurrent_runs == 1
        finally:
            runner.stop_background_task("group-a")
            runner.stop_background_task("group-b")
            runner.stop_background_task_runner()
            await asyncio.sleep(0.01)

    asyncio.run(_scenario())


def test_resource_key_sequence_prioritizes_lower_sequence_task() -> None:
    """Within a resource group, lower sequence task should run before higher sequence task."""

    async def _scenario() -> None:
        runner = BackgroundTaskRunner()
        call_order: list[str] = []

        async def _run_low() -> None:
            call_order.append("low")
            await asyncio.sleep(0.03)

        async def _run_high() -> None:
            call_order.append("high")
            await asyncio.sleep(0.01)

        runner.start_background_task_runner()
        runner.register_background_task(
            _build_task(
                "seq-high",
                _run_high,
                interval_seconds=0.01,
                resource_key="shared-resource",
                resource_sequence=20,
            )
        )
        runner.register_background_task(
            _build_task(
                "seq-low",
                _run_low,
                interval_seconds=0.01,
                resource_key="shared-resource",
                resource_sequence=10,
            )
        )

        # Intentionally start high first; scheduler should still prioritize low.
        runner.start_background_task("seq-high")
        runner.start_background_task("seq-low")

        try:
            await asyncio.sleep(0.08)
            assert call_order
            assert call_order[0] == "low"
        finally:
            runner.stop_background_task("seq-low")
            runner.stop_background_task("seq-high")
            runner.stop_background_task_runner()
            await asyncio.sleep(0.01)

    asyncio.run(_scenario())


def test_resource_group_tasks_keep_event_loop_responsive() -> None:
    """Resource-group scheduling should not block unrelated event-loop progress."""

    async def _scenario() -> None:
        runner = BackgroundTaskRunner()

        def _run_sync() -> None:
            import time

            time.sleep(0.03)

        runner.start_background_task_runner()
        runner.register_background_task(
            _build_task(
                "group-sync-a",
                _run_sync,
                interval_seconds=0.01,
                resource_key="shared-resource",
                resource_sequence=10,
            )
        )
        runner.register_background_task(
            _build_task(
                "group-sync-b",
                _run_sync,
                interval_seconds=0.01,
                resource_key="shared-resource",
                resource_sequence=20,
            )
        )
        runner.start_background_task("group-sync-a")
        runner.start_background_task("group-sync-b")

        ticker_count = 0

        async def _ticker() -> None:
            nonlocal ticker_count
            for _ in range(8):
                await asyncio.sleep(0.01)
                ticker_count += 1

        try:
            await _ticker()
            assert ticker_count == 8
        finally:
            runner.stop_background_task("group-sync-a")
            runner.stop_background_task("group-sync-b")
            runner.stop_background_task_runner()
            await asyncio.sleep(0.01)

    asyncio.run(_scenario())


def test_stop_after_success_stops_loop_without_self_cancelling_run() -> None:
    """One-shot tasks should stop after success without cancelling their active run task."""

    async def _scenario() -> None:
        runner = BackgroundTaskRunner()
        task_id = "one-shot-success"
        run_completed = asyncio.Event()

        async def _run_once() -> None:
            run_completed.set()

        runner.start_background_task_runner()
        runner.register_background_task(
            _build_task(
                task_id,
                _run_once,
                interval_seconds=0.01,
                stop_after_success=True,
            )
        )
        runner.start_background_task(task_id)

        try:
            await asyncio.wait_for(run_completed.wait(), timeout=0.2)
            await asyncio.sleep(0.03)

            status = runner.get_background_task_status(task_id)
            state = runner._registry[task_id]

            assert status.is_running is False
            assert status.total_runs == 1
            assert status.last_run_succeeded_at is not None
            assert status.last_error_message is None
            assert state.run_in_progress is False
            assert state.run_handle is None
        finally:
            runner.stop_background_task(task_id)
            runner.stop_background_task_runner()
            await asyncio.sleep(0.01)

    asyncio.run(_scenario())


def test_resource_group_periodic_siblings_continue_after_one_shot_bootstrap() -> None:
    """One-shot lower-sequence bootstrap should not starve later periodic siblings."""

    async def _scenario() -> None:
        runner = BackgroundTaskRunner()
        calls: list[str] = []

        async def _bootstrap_once() -> None:
            calls.append("bootstrap")
            await asyncio.sleep(0.005)

        async def _periodic_a() -> None:
            calls.append("periodic-a")
            await asyncio.sleep(0.005)

        async def _periodic_b() -> None:
            calls.append("periodic-b")
            await asyncio.sleep(0.005)

        runner.start_background_task_runner()
        runner.register_background_task(
            _build_task(
                "bootstrap",
                _bootstrap_once,
                interval_seconds=0.01,
                resource_key="shared-resource",
                resource_sequence=5,
                stop_after_success=True,
            )
        )
        runner.register_background_task(
            _build_task(
                "periodic-a",
                _periodic_a,
                interval_seconds=0.01,
                resource_key="shared-resource",
                resource_sequence=10,
            )
        )
        runner.register_background_task(
            _build_task(
                "periodic-b",
                _periodic_b,
                interval_seconds=0.01,
                resource_key="shared-resource",
                resource_sequence=20,
            )
        )
        runner.start_background_task("bootstrap")
        runner.start_background_task("periodic-a")
        runner.start_background_task("periodic-b")

        try:
            await asyncio.sleep(0.14)

            bootstrap_status = runner.get_background_task_status("bootstrap")
            periodic_a_status = runner.get_background_task_status("periodic-a")
            periodic_b_status = runner.get_background_task_status("periodic-b")

            assert bootstrap_status.is_running is False
            assert bootstrap_status.total_runs == 1
            assert periodic_a_status.total_runs >= 2
            assert periodic_b_status.total_runs >= 2
            assert calls[0] == "bootstrap"
        finally:
            runner.stop_background_task("bootstrap")
            runner.stop_background_task("periodic-a")
            runner.stop_background_task("periodic-b")
            runner.stop_background_task_runner()
            await asyncio.sleep(0.01)

    asyncio.run(_scenario())
