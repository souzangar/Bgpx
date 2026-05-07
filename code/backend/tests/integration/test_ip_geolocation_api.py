"""Integration tests for IP geolocation API route wiring and payload contracts."""

from pathlib import Path
import sys

from fastapi.testclient import TestClient


BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from main import create_app
from services.background_task_runner import reset_background_task_runner_for_tests


def test_get_ipinfo_lookup_returns_contract_payload() -> None:
    """GET /api/ipinfo should accept JSON body and return lookup contract fields."""
    reset_background_task_runner_for_tests()

    try:
        app = create_app()
        with TestClient(app) as client:
            response = client.request(
                "GET",
                "/api/ipinfo",
                json={"type": "ip", "value": "1.1.1.1"},
            )

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


def test_get_ipinfo_lookup_supports_asn_type() -> None:
    """GET /api/ipinfo should accept ASN JSON body and return contract payload."""
    reset_background_task_runner_for_tests()

    try:
        app = create_app()
        with TestClient(app) as client:
            response = client.request(
                "GET",
                "/api/ipinfo",
                json={"type": "asn", "value": "AS13335"},
            )

        assert response.status_code == 200
        payload = response.json()

        assert payload["status"] in {"success", "failure"}
        assert payload["service_state"] in {"loading", "ready", "failed"}
        if payload["status"] == "success":
            assert payload["resolution_state"] in {"found", "initializing_db", "not_found"}
            assert payload["data"]["asn"] == "AS13335"
            assert isinstance(payload["data"]["items"], list)
            assert isinstance(payload["data"]["total"], int)
            if payload["data"]["items"]:
                first = payload["data"]["items"][0]
                assert set(first.keys()) == {
                    "network",
                    "country",
                    "country_code",
                    "continent",
                    "continent_code",
                }
        else:
            assert payload["service_state"] == "failed"
    finally:
        reset_background_task_runner_for_tests()


def test_get_ipinfo_lookup_supports_country_type_as_country_code() -> None:
    """GET /api/ipinfo should accept country type and treat value as country code."""
    reset_background_task_runner_for_tests()

    try:
        app = create_app()
        with TestClient(app) as client:
            response = client.request(
                "GET",
                "/api/ipinfo",
                json={"type": "country", "value": "US"},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] in {"success", "failure"}
        assert payload["service_state"] in {"loading", "ready", "failed"}

        if payload["status"] == "success":
            assert payload["resolution_state"] in {"found", "initializing_db", "not_found"}
            assert payload["data"]["country"] == "US"
            assert isinstance(payload["data"]["items"], list)
            assert isinstance(payload["data"]["total"], int)
            if payload["data"]["items"]:
                first = payload["data"]["items"][0]
                assert set(first.keys()) == {
                    "network",
                    "continent",
                    "continent_code",
                    "asn",
                }
        else:
            assert payload["service_state"] == "failed"
    finally:
        reset_background_task_runner_for_tests()


def test_get_geo_status_returns_contract_payload() -> None:
    """GET /api/ipinfo_status should be reachable and return status contract fields."""
    reset_background_task_runner_for_tests()

    try:
        app = create_app()
        with TestClient(app) as client:
            response = client.get("/api/ipinfo_status")

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
