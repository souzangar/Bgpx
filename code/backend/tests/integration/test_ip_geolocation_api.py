"""Integration tests for IP geolocation API route wiring and payload contracts."""

from pathlib import Path
import sys

from fastapi.testclient import TestClient


BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from main import create_app
from services.background_task_runner import reset_background_task_runner_for_tests


def test_get_geo_lookup_returns_contract_payload() -> None:
    """GET /api/geo/lookup should be reachable and return lookup contract fields."""
    reset_background_task_runner_for_tests()

    try:
        app = create_app()
        with TestClient(app) as client:
            response = client.get("/api/geo/lookup", params={"ip": "1.1.1.1"})

        assert response.status_code == 200
        payload = response.json()

        assert payload["status"] in {"success", "failure"}
        assert payload["service_state"] in {"loading", "ready", "failed"}

        if payload["status"] == "success":
            assert payload["resolution_state"] in {"found", "initializing_db", "not_found"}
            assert isinstance(payload["data"], dict)
            assert payload["data"]["ip"] == "1.1.1.1"
        else:
            assert payload["service_state"] == "failed"
            assert isinstance(payload["error"], dict)
            assert payload["error"]["code"] != ""
    finally:
        reset_background_task_runner_for_tests()


def test_get_geo_status_returns_contract_payload() -> None:
    """GET /api/geo/status should be reachable and return status contract fields."""
    reset_background_task_runner_for_tests()

    try:
        app = create_app()
        with TestClient(app) as client:
            response = client.get("/api/geo/status")

        assert response.status_code == 200
        payload = response.json()

        assert payload["service_state"] in {"loading", "ready", "failed"}
        assert isinstance(payload["counters"], dict)
        assert set(payload["counters"].keys()) == {"total", "loaded", "malformed"}
        assert isinstance(payload["counters"]["total"], int)
        assert isinstance(payload["counters"]["loaded"], int)
        assert isinstance(payload["counters"]["malformed"], int)
    finally:
        reset_background_task_runner_for_tests()
