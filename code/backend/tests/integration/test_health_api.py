"""Integration tests for the health API router wiring and response."""

from pathlib import Path
import sys

from fastapi.testclient import TestClient


BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from main import create_app


def test_get_health_returns_ok_payload() -> None:
    """GET /api/health should return the expected backend health payload."""
    app = create_app()

    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "bgpx-backend"}
