"""FastAPI lifespan wiring for IP geolocation background tasks.

This module keeps app lifecycle orchestration separate from ``main.py`` while
preserving existing task IDs, intervals, and ordering semantics.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from apps.ip_geolocation import get_ip_geolocation_service
from models.background_task_runner import BackgroundTaskDefinition
from services.background_task_runner.background_task_config_service import get_background_tasks_config
from services.background_task_runner import get_background_task_runner
from services.ip_geolocation.ip_geolocation_data_downloader import IpGeolocationDataDownloader
from services.ip_geolocation.ip_geolocation_data_refresher import IpGeolocationDataRefresher


IP_GEO_BOOTSTRAP_TASK_KEY = "bootstrap_once"
IP_GEO_IPINFO_GZ_DOWNLOADER_TASK_KEY = "ipinfo_gz_downloader"
IP_GEO_REFRESH_TASK_KEY = "data_refresh"


def _register_background_task_idempotent(task: BackgroundTaskDefinition) -> None:
    """Register one task while tolerating prior registration in the same process."""
    runner = get_background_task_runner()
    try:
        runner.register_background_task(task)
    except ValueError:
        # Task already registered in this process; keep lifecycle idempotent.
        pass


def _stop_background_task_idempotent(task_id: str) -> None:
    """Stop one task while tolerating missing registration."""
    runner = get_background_task_runner()
    try:
        runner.stop_background_task(task_id)
    except KeyError:
        pass


def _unregister_background_task_idempotent(task_id: str) -> None:
    """Unregister one task while tolerating missing registration."""
    runner = get_background_task_runner()
    try:
        runner.unregister_background_task(task_id)
    except KeyError:
        pass


@asynccontextmanager
async def app_lifespan(_app: FastAPI):
    """Manage process-local IP geolocation background services for app lifecycle."""
    runner = get_background_task_runner()
    runner.start_background_task_runner()

    ip_geolocation_service = get_ip_geolocation_service()
    ip_geolocation_service.initialize_ip_geolocation_dataset()
    ip_geolocation_downloader = IpGeolocationDataDownloader()
    ip_geolocation_refresher = IpGeolocationDataRefresher(
        publish_snapshot=ip_geolocation_service.publish_snapshot,
        is_snapshot_equivalent=ip_geolocation_service.is_snapshot_equivalent,
        apply_snapshot_delta=ip_geolocation_service.apply_snapshot_delta,
    )

    configured_ip_geo = get_background_tasks_config().ip_geolocation

    bootstrap_completed = False

    async def _run_bootstrap_once() -> None:
        nonlocal bootstrap_completed
        if bootstrap_completed:
            return

        await asyncio.to_thread(ip_geolocation_downloader.run_once)
        await asyncio.to_thread(ip_geolocation_refresher.run_once)

        bootstrap_completed = True

    run_callable_map = {
        IP_GEO_BOOTSTRAP_TASK_KEY: _run_bootstrap_once,
        IP_GEO_IPINFO_GZ_DOWNLOADER_TASK_KEY: ip_geolocation_downloader.run_once,
        IP_GEO_REFRESH_TASK_KEY: ip_geolocation_refresher.run_once,
    }

    configured_tasks_by_key = {task.task_key: task for task in configured_ip_geo.tasks}
    enabled_tasks: list[BackgroundTaskDefinition] = []

    for required_task_key in (
        IP_GEO_BOOTSTRAP_TASK_KEY,
        IP_GEO_IPINFO_GZ_DOWNLOADER_TASK_KEY,
        IP_GEO_REFRESH_TASK_KEY,
    ):
        configured_task = configured_tasks_by_key.get(required_task_key)
        if configured_task is None:
            raise RuntimeError(
                f"background_tasks_config: required task '{required_task_key}' is missing"
            )

        if not configured_task.enabled:
            continue

        run_once = run_callable_map.get(required_task_key)
        if run_once is None:
            raise RuntimeError(
                f"background_tasks_config: no runnable is mapped for task '{required_task_key}'"
            )

        enabled_tasks.append(
            BackgroundTaskDefinition(
                task_id=configured_task.task_id,
                interval_seconds=configured_task.interval_seconds,
                run_once=run_once,
                resource_key=configured_ip_geo.resource_key,
                resource_sequence=configured_task.resource_sequence,
                stop_after_success=configured_task.stop_after_success,
            )
        )

    if not enabled_tasks:
        raise RuntimeError("background_tasks_config: at least one ip_geolocation task must be enabled")

    enabled_task_ids = tuple(task.task_id for task in enabled_tasks)

    for task in enabled_tasks:
        _register_background_task_idempotent(task)

    for task_id in enabled_task_ids:
        runner.start_background_task(task_id)

    try:
        yield
    finally:
        for task_id in enabled_task_ids:
            _stop_background_task_idempotent(task_id)

        for task_id in enabled_task_ids:
            _unregister_background_task_idempotent(task_id)

        runner.stop_background_task_runner()


__all__ = ["app_lifespan"]
