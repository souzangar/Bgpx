"""Integration tests for FastAPI lifespan wiring of background task runner."""

from pathlib import Path
import sys

from fastapi.testclient import TestClient


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
