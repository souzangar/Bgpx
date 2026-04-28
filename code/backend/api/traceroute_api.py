"""Traceroute API router that bridges API layer to traceroute app layer."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter

from apps.traceroute import run_traceroute

router = APIRouter()


@router.get("/traceroute", tags=["traceroute"])
def traceroute_host(
    host: str,
) -> dict[str, object]:
    """Run traceroute for target host and return normalized traceroute payload."""
    result = run_traceroute(host)
    return asdict(result)
