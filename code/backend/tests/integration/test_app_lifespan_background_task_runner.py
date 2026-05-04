"""Integration tests for FastAPI lifespan wiring of background task runner."""

from pathlib import Path
import sys

from fastapi.testclient import TestClient
import pytest


BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from main import create_app
from services.background_task_runner import (
    get_background_task_runner,
    reset_background_task_runner_for_tests,
)


def test_app_lifespan_starts_and_stops_background_task_runner() -> None:
    """App startup should start runner and shutdown should stop it."""
    reset_background_task_runner_for_tests()

    try:
        runner = get_background_task_runner()
        assert runner._runner_started is False

        app = create_app()
        with TestClient(app) as client:
            response = client.get("/api/health")
            assert response.status_code == 200
            assert runner._runner_started is True

        assert runner._runner_started is False
    finally:
        reset_background_task_runner_for_tests()


def test_app_lifespan_registers_and_cleans_ip_geo_refresh_task() -> None:
    """Lifespan should start IP geo task while app is running and clean it on shutdown."""
    reset_background_task_runner_for_tests()

    try:
        runner = get_background_task_runner()
        app = create_app()

        with TestClient(app) as client:
            response = client.get("/api/health")
            assert response.status_code == 200

            status = runner.get_background_task_status("ip_geolocation_source_watch")
            assert status.task_id == "ip_geolocation_source_watch"
            assert status.is_running is True

        with TestClient(app) as client:
            response = client.get("/api/health")
            assert response.status_code == 200

            status = runner.get_background_task_status("ip_geolocation_source_watch")
            assert status.is_running is True

        with TestClient(app):
            pass

        with pytest.raises(KeyError):
            runner.get_background_task_status("ip_geolocation_source_watch")
    finally:
        reset_background_task_runner_for_tests()
