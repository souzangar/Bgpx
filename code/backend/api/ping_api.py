"""Ping API router that bridges API layer to ping app layer."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter

from apps.ping import run_ping

router = APIRouter()


@router.get("/ping", tags=["ping"])
def ping_host(host: str) -> dict[str, object]:
    """Run ping for target host and return normalized ping payload."""
    result = run_ping(host)
    return asdict(result)
