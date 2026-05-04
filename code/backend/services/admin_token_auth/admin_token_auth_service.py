"""Core admin token authentication parsing and validation service."""

from __future__ import annotations

import hmac
import os

from fastapi import Header, HTTPException, status

from models.admin_token_auth import (
    AdminTokenAuthConfigStateModel,
    AdminTokenValidationReason,
    AdminTokenValidationResultModel,
)


AdminTokenEntry = tuple[str, str | None]


def get_configured_admin_tokens() -> tuple[AdminTokenEntry, ...]:
    """Return normalized, de-duplicated admin token entries from environment config."""
    raw_config = os.getenv("BGPX_ADMIN_TOKENS", "")
    if not raw_config.strip():
        return ()

    entries: list[AdminTokenEntry] = []
    seen_tokens: set[str] = set()

    for raw_entry in raw_config.replace(";", "\n").splitlines():
        candidate = raw_entry.strip()
        if not candidate:
            continue

        if "|" in candidate:
            token_part, note_part = candidate.split("|", 1)
            token = token_part.strip()
            note = note_part.strip() or None
        else:
            token = candidate
            note = None

        if not token or token in seen_tokens:
            continue

        seen_tokens.add(token)
        entries.append((token, note))

    return tuple(entries)


def get_admin_token_auth_config_state() -> AdminTokenAuthConfigStateModel:
    """Expose auth configuration observability state."""
    configured_tokens = get_configured_admin_tokens()
    return AdminTokenAuthConfigStateModel(
        is_configured=len(configured_tokens) > 0,
        configured_token_count=len(configured_tokens),
    )


def validate_admin_token(provided_token: str | None) -> AdminTokenValidationResultModel:
    """Validate provided token against configured admin token inventory."""
    configured_tokens = get_configured_admin_tokens()
    if not configured_tokens:
        return AdminTokenValidationResultModel(
            is_authorized=False,
            reason="missing_config",
        )

    normalized_token = (provided_token or "").strip()
    if not normalized_token:
        return AdminTokenValidationResultModel(
            is_authorized=False,
            reason="missing_token",
        )

    for configured_token, note in configured_tokens:
        if hmac.compare_digest(normalized_token, configured_token):
            return AdminTokenValidationResultModel(
                is_authorized=True,
                reason="ok",
                matched_note=note,
            )

    return AdminTokenValidationResultModel(
        is_authorized=False,
        reason="invalid_token",
    )


def require_admin_token(x_admin_token: str | None = Header(default=None, alias="X-Admin-Token")) -> AdminTokenValidationResultModel:
    """FastAPI dependency guard for admin-protected endpoints."""
    result = validate_admin_token(x_admin_token)
    if result.is_authorized:
        return result

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=_build_auth_failure_detail(result.reason),
    )


def _build_auth_failure_detail(reason: AdminTokenValidationReason) -> str:
    """Map deterministic auth-failure reason to a user-safe 401 detail message."""
    if reason == "missing_config":
        return "Admin token authentication is not configured"
    if reason == "missing_token":
        return "Missing X-Admin-Token header"
    return "Invalid admin token"


__all__ = [
    "AdminTokenEntry",
    "get_admin_token_auth_config_state",
    "get_configured_admin_tokens",
    "require_admin_token",
    "validate_admin_token",
]
