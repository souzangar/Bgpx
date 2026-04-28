"""Integration tests for ping API endpoint behavior."""

from __future__ import annotations

import os
from pathlib import Path
import sys

import httpx
import pytest
from fastapi.testclient import TestClient


BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from main import create_app


def _call_live_ping_api(host: str) -> dict[str, object]:
    """Call running API endpoint over HTTP(S), same style as Bruno requests."""
    base_url = os.getenv("BGPX_API_BASE_URL", "https://localhost").rstrip("/")
    url = f"{base_url}/api/ping"
    ca_bundle = os.getenv("BGPX_CA_BUNDLE")
    verify: bool | str = ca_bundle if ca_bundle else True

    try:
        response = httpx.get(
            url,
            params={"host": host},
            timeout=5.0,
            verify=verify,
        )
    except httpx.RequestError as exc:
        pytest.skip(f"Live API endpoint not reachable at {url}: {exc}")

    assert response.status_code == 200
    return response.json()


def test_get_ping_returns_success_for_reachable_target() -> None:
    """GET /api/ping should return success for the known reachable host."""
    app = create_app()

    with TestClient(app) as client:
        response = client.get("/api/ping", params={"host": "217.218.127.127"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"] == "success"
    assert payload["message"] == "ping success"
    assert payload["ttl"] is not None
    assert isinstance(payload["ttl"], int)
    assert set(payload.keys()) == {"result", "ping_time_ms", "ttl", "message"}


def test_get_ping_returns_timeout_for_unreachable_target() -> None:
    """GET /api/ping should return timeout status for the unreachable host."""
    app = create_app()

    with TestClient(app) as client:
        response = client.get("/api/ping", params={"host": "217.217.127.255"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"] == "success"
    assert payload["message"] == "ping timeout"
    assert set(payload.keys()) == {"result", "ping_time_ms", "ttl", "message"}


