"""Integration tests for traceroute API endpoint behavior."""

from __future__ import annotations

import os
from pathlib import Path
import sys

import httpx
import pytest


BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

def _call_live_traceroute_api(host: str, *, max_hops: int = 30, timeout: float = 2, count: int = 2) -> dict[str, object]:
    """Call running traceroute API endpoint over HTTP(S), same style as Bruno requests."""
    base_url = os.getenv("BGPX_API_BASE_URL", "https://localhost").rstrip("/")
    url = f"{base_url}/api/traceroute"

    try:
        response = httpx.get(
            url,
            params={"host": host, "max_hops": max_hops, "timeout": timeout, "count": count},
            timeout=15.0,
            verify=False,
        )
    except httpx.RequestError as exc:
        pytest.skip(f"Live API endpoint not reachable at {url}: {exc}")

    assert response.status_code == 200
    return response.json()


def test_get_traceroute_returns_valid_payload_for_reachable_target() -> None:
    """GET /api/traceroute should return a valid traceroute payload for reachable host."""
    payload = _call_live_traceroute_api("217.218.127.127", max_hops=20, timeout=1.5, count=2)

    assert set(payload.keys()) == {"result", "hops", "message"}
    assert payload["result"] in {"success", "failure"}
    assert isinstance(payload["hops"], list)
    assert isinstance(payload["message"], str)

    if payload["result"] == "success":
        assert len(payload["hops"]) > 0
    else:
        message = payload["message"].strip().lower()
        assert message != ""

        if "root privileges" in message or "insufficient permissions" in message or "not permitted" in message:
            pytest.fail(
                "Traceroute runtime is not working: missing raw socket privileges. "
                "Run API process with required privileges/capabilities and retry. "
                f"Got message: {payload['message']}"
            )

        pytest.fail(
            "Traceroute reachable-target integration failed. "
            f"Expected success but got failure message: {payload['message']}"
        )



