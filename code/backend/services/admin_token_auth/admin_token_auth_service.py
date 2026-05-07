"""Core admin token authentication parsing and validation service."""

from __future__ import annotations

import hmac
import json
from pathlib import Path
from typing import Any

from fastapi import Header, HTTPException, status

from models.admin_token_auth import (
    AdminTokenAuthConfigStateModel,
    AdminTokenValidationReason,
    AdminTokenValidationResultModel,
)


AdminTokenEntry = tuple[str, str | None]

ADMIN_TOKEN_AUTH_CONFIG_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "configs" / "admin_token_auth_config.json"
)

_CACHED_TOKENS: tuple[AdminTokenEntry, ...] | None = None
_CONFIG_MTIME_NS: int | None = None


def _read_config_mtime_ns() -> int | None:
    try:
        return ADMIN_TOKEN_AUTH_CONFIG_PATH.stat().st_mtime_ns
    except OSError:
        return None


def _load_raw_config() -> dict[str, Any]:
    try:
        with ADMIN_TOKEN_AUTH_CONFIG_PATH.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
    except Exception as exc:
        raise RuntimeError(
            f"Failed to load admin token auth config from '{ADMIN_TOKEN_AUTH_CONFIG_PATH}': {exc}"
        ) from exc

    if not isinstance(loaded, dict):
        raise RuntimeError(
            f"Admin token auth config file '{ADMIN_TOKEN_AUTH_CONFIG_PATH}' must contain a JSON object"
        )
    return loaded


def _parse_tokens(raw: dict[str, Any]) -> tuple[AdminTokenEntry, ...]:
    version = raw.get("version")
    if not isinstance(version, int) or version <= 0:
        raise RuntimeError("admin_token_auth_config: 'version' must be a positive integer")

    tokens_any = raw.get("tokens")
    if not isinstance(tokens_any, list):
        raise RuntimeError("admin_token_auth_config: 'tokens' must be an array")

    parsed: list[AdminTokenEntry] = []
    seen_tokens: set[str] = set()

    for index, token_entry_any in enumerate(tokens_any):
        if not isinstance(token_entry_any, dict):
            raise RuntimeError(
                f"admin_token_auth_config: token entry at index {index} must be an object"
            )

        token_any = token_entry_any.get("token")
        if not isinstance(token_any, str) or not token_any.strip():
            raise RuntimeError(
                f"admin_token_auth_config: token entry at index {index} must have a non-empty 'token'"
            )
        token = token_any.strip()

        note_any = token_entry_any.get("note")
        note: str | None = None
        if note_any is not None:
            if not isinstance(note_any, str) or not note_any.strip():
                raise RuntimeError(
                    f"admin_token_auth_config: token entry at index {index} has invalid 'note'"
                )
            note = note_any.strip()

        if token in seen_tokens:
            continue

        seen_tokens.add(token)
        parsed.append((token, note))

    return tuple(parsed)


def get_configured_admin_tokens() -> tuple[AdminTokenEntry, ...]:
    """Return validated, de-duplicated admin token entries from JSON config file."""
    global _CACHED_TOKENS, _CONFIG_MTIME_NS

    current_mtime_ns = _read_config_mtime_ns()
    if _CACHED_TOKENS is not None and _CONFIG_MTIME_NS == current_mtime_ns:
        return _CACHED_TOKENS

    parsed = _parse_tokens(_load_raw_config())
    _CACHED_TOKENS = parsed
    _CONFIG_MTIME_NS = current_mtime_ns
    return parsed


def get_admin_token_auth_config_state() -> AdminTokenAuthConfigStateModel:
    """Expose auth configuration observability state."""
    configured_tokens = get_configured_admin_tokens()
    return AdminTokenAuthConfigStateModel(
        is_configured=len(configured_tokens) > 0,
        configured_token_count=len(configured_tokens),
    )


def validate_admin_token(provided_token: str | None) -> AdminTokenValidationResultModel:
    """Validate provided token against configured admin token inventory."""
    try:
        configured_tokens = get_configured_admin_tokens()
    except RuntimeError:
        configured_tokens = ()

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


def reset_admin_token_auth_config_cache_for_tests() -> None:
    """Reset cached admin token auth config state for test isolation."""
    global _CACHED_TOKENS, _CONFIG_MTIME_NS
    _CACHED_TOKENS = None
    _CONFIG_MTIME_NS = None


__all__ = [
    "AdminTokenEntry",
    "get_admin_token_auth_config_state",
    "get_configured_admin_tokens",
    "require_admin_token",
    "reset_admin_token_auth_config_cache_for_tests",
    "validate_admin_token",
]
