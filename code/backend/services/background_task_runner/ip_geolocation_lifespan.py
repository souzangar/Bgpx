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
from services.background_task_runner import get_background_task_runner
from services.ip_geolocation.ip_geolocation_data_downloader import IpGeolocationDataDownloader
from services.ip_geolocation.ip_geolocation_data_refresher import IpGeolocationDataRefresher
from services.logging import configure_backend_logging


IP_GEO_BOOTSTRAP_TASK_ID = "ip_geolocation_bootstrap_once"
IP_GEO_REFRESH_TASK_ID = "ip_geolocation_data_refresh"
IP_GEO_REFRESH_INTERVAL_SECONDS = 5.0
IP_GEO_IPINFO_GZ_DOWNLOADER_TASK_ID = "ip_geolocation_ipinfo_gz_downloader"
IP_GEO_IPINFO_GZ_DOWNLOADER_INTERVAL_SECONDS = 5.0
IP_GEO_BOOTSTRAP_INTERVAL_SECONDS = 0.5
IP_GEO_DATASET_RESOURCE_KEY = "ip_geolocation_database_handler"
IP_GEO_BOOTSTRAP_SEQUENCE = 5
IP_GEO_IPINFO_GZ_DOWNLOADER_SEQUENCE = 10
IP_GEO_REFRESH_SEQUENCE = 20


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
    configure_backend_logging()
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

    bootstrap_completed = False

    async def _run_bootstrap_once() -> None:
        nonlocal bootstrap_completed
        if bootstrap_completed:
            return

        await asyncio.to_thread(ip_geolocation_downloader.run_once)
        await asyncio.to_thread(ip_geolocation_refresher.run_once)

        bootstrap_completed = True

    ip_geo_bootstrap_task = BackgroundTaskDefinition(
        task_id=IP_GEO_BOOTSTRAP_TASK_ID,
        interval_seconds=IP_GEO_BOOTSTRAP_INTERVAL_SECONDS,
        run_once=_run_bootstrap_once,
        resource_key=IP_GEO_DATASET_RESOURCE_KEY,
        resource_sequence=IP_GEO_BOOTSTRAP_SEQUENCE,
        stop_after_success=True,
    )

    ip_geo_ipinfo_gz_downloader_task = BackgroundTaskDefinition(
        task_id=IP_GEO_IPINFO_GZ_DOWNLOADER_TASK_ID,
        interval_seconds=IP_GEO_IPINFO_GZ_DOWNLOADER_INTERVAL_SECONDS,
        run_once=ip_geolocation_downloader.run_once,
        resource_key=IP_GEO_DATASET_RESOURCE_KEY,
        resource_sequence=IP_GEO_IPINFO_GZ_DOWNLOADER_SEQUENCE,
    )

    ip_geo_refresh_task = BackgroundTaskDefinition(
        task_id=IP_GEO_REFRESH_TASK_ID,
        interval_seconds=IP_GEO_REFRESH_INTERVAL_SECONDS,
        run_once=ip_geolocation_refresher.run_once,
        resource_key=IP_GEO_DATASET_RESOURCE_KEY,
        resource_sequence=IP_GEO_REFRESH_SEQUENCE,
    )

    tasks = (
        ip_geo_bootstrap_task,
        ip_geo_ipinfo_gz_downloader_task,
        ip_geo_refresh_task,
    )

    for task in tasks:
        _register_background_task_idempotent(task)

    runner.start_background_task(IP_GEO_BOOTSTRAP_TASK_ID)
    runner.start_background_task(IP_GEO_IPINFO_GZ_DOWNLOADER_TASK_ID)
    runner.start_background_task(IP_GEO_REFRESH_TASK_ID)

    try:
        yield
    finally:
        for task_id in (
            IP_GEO_BOOTSTRAP_TASK_ID,
            IP_GEO_IPINFO_GZ_DOWNLOADER_TASK_ID,
            IP_GEO_REFRESH_TASK_ID,
        ):
            _stop_background_task_idempotent(task_id)

        for task_id in (
            IP_GEO_BOOTSTRAP_TASK_ID,
            IP_GEO_IPINFO_GZ_DOWNLOADER_TASK_ID,
            IP_GEO_REFRESH_TASK_ID,
        ):
            _unregister_background_task_idempotent(task_id)

        runner.stop_background_task_runner()


__all__ = ["app_lifespan"]
