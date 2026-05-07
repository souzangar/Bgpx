"""Integration tests for IP geolocation API route wiring and payload contracts."""

from pathlib import Path
import json
import sys

from dataclasses import dataclass

from fastapi.testclient import TestClient


BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from main import create_app
from services.background_task_runner import reset_background_task_runner_for_tests
from services.admin_token_auth import reset_admin_token_auth_config_cache_for_tests


def _write_admin_token_config(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "admin_token_auth_config.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


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


def test_get_ipinfo_lookup_supports_continent_type_as_continent_code() -> None:
    """GET /api/ipinfo should accept continent type and treat value as continent code."""
    reset_background_task_runner_for_tests()

    try:
        app = create_app()
        with TestClient(app) as client:
            response = client.request(
                "GET",
                "/api/ipinfo",
                json={"type": "continent", "value": "EU"},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] in {"success", "failure"}
        assert payload["service_state"] in {"loading", "ready", "failed"}

        if payload["status"] == "success":
            assert payload["resolution_state"] in {"found", "initializing_db", "not_found"}
            assert payload["data"]["continent"] == "EU"
            assert isinstance(payload["data"]["items"], list)
            assert isinstance(payload["data"]["total"], int)
            if payload["data"]["items"]:
                first = payload["data"]["items"][0]
                assert set(first.keys()) == {
                    "network",
                    "country",
                    "country_code",
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


def test_post_ipinfo_update_force_triggers_manual_downloader_cycle(monkeypatch, tmp_path: Path) -> None:
    """POST /api/ipinfo_update should be reachable and return force-update payload."""
    reset_background_task_runner_for_tests()
    config_path = _write_admin_token_config(
        tmp_path,
        {"version": 1, "tokens": [{"token": "token_admin", "note": "test-admin"}]},
    )
    monkeypatch.setattr(
        "services.admin_token_auth.admin_token_auth_service.ADMIN_TOKEN_AUTH_CONFIG_PATH",
        config_path,
    )
    reset_admin_token_auth_config_cache_for_tests()

    @dataclass(frozen=True)
    class _StubForceUpdateResponse:
        status: str
        action: str
        attempts: int
        success_count: int
        failure_count: int
        last_attempt_at: str | None
        last_succeeded_at: str | None
        last_error: str | None

    monkeypatch.setattr(
        "api.ip_geolocation_api.force_ipinfo_gz_update",
        lambda: _StubForceUpdateResponse(
            status="success",
            action="ipinfo_gz_force_update",
            attempts=1,
            success_count=1,
            failure_count=0,
            last_attempt_at=None,
            last_succeeded_at=None,
            last_error=None,
        ),
    )

    try:
        app = create_app()
        with TestClient(app) as client:
            response = client.post(
                "/api/ipinfo_update",
                headers={"X-Admin-Token": "token_admin"},
            )

        assert response.status_code == 200
        payload = response.json()

        assert payload["status"] in {"success", "failure"}
        assert payload["action"] == "ipinfo_gz_force_update"
        assert isinstance(payload["attempts"], int)
        assert isinstance(payload["success_count"], int)
        assert isinstance(payload["failure_count"], int)
        assert "last_attempt_at" in payload
        assert "last_succeeded_at" in payload
        assert "last_error" in payload
    finally:
        reset_admin_token_auth_config_cache_for_tests()
        reset_background_task_runner_for_tests()


def test_post_ipinfo_update_rejects_missing_admin_token(monkeypatch, tmp_path: Path) -> None:
    """POST /api/ipinfo_update should reject requests without admin token header."""
    reset_background_task_runner_for_tests()
    config_path = _write_admin_token_config(
        tmp_path,
        {"version": 1, "tokens": [{"token": "token_admin", "note": "test-admin"}]},
    )
    monkeypatch.setattr(
        "services.admin_token_auth.admin_token_auth_service.ADMIN_TOKEN_AUTH_CONFIG_PATH",
        config_path,
    )
    reset_admin_token_auth_config_cache_for_tests()

    try:
        app = create_app()
        with TestClient(app) as client:
            response = client.post("/api/ipinfo_update")

        assert response.status_code == 401
        assert response.json().get("detail") == "Missing X-Admin-Token header"
    finally:
        reset_admin_token_auth_config_cache_for_tests()
        reset_background_task_runner_for_tests()
