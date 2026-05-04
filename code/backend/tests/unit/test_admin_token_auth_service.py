"""Unit tests for admin token auth service parsing and validation behavior."""

from __future__ import annotations

from pathlib import Path
import sys

from fastapi import HTTPException
import pytest


BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.admin_token_auth import (
    get_admin_token_auth_config_state,
    get_configured_admin_tokens,
    require_admin_token,
    validate_admin_token,
)


def test_get_configured_admin_tokens_supports_semicolon_and_newline_and_deduplicates(monkeypatch) -> None:
    """Parser should normalize separators, retain first note, and de-duplicate tokens."""
    monkeypatch.setenv(
        "BGPX_ADMIN_TOKENS",
        " token_a|person a ;token_b|person b\n token_a|duplicate note ; ; malformed| ; token_c ",
    )

    entries = get_configured_admin_tokens()

    assert len(entries) == 4
    assert entries[0] == ("token_a", "person a")
    assert entries[1] == ("token_b", "person b")
    assert entries[2] == ("malformed", None)
    assert entries[3] == ("token_c", None)


def test_validate_admin_token_returns_missing_config_when_env_missing(monkeypatch) -> None:
    """Validation should fail-closed when config is missing/empty."""
    monkeypatch.delenv("BGPX_ADMIN_TOKENS", raising=False)

    result = validate_admin_token("token_a")

    assert result.is_authorized is False
    assert result.reason == "missing_config"
    assert result.matched_note is None


def test_validate_admin_token_returns_missing_token_when_request_token_absent(monkeypatch) -> None:
    """Configured tokens with absent provided token should return missing_token."""
    monkeypatch.setenv("BGPX_ADMIN_TOKENS", "token_a|person a")

    result = validate_admin_token(None)

    assert result.is_authorized is False
    assert result.reason == "missing_token"
    assert result.matched_note is None


def test_validate_admin_token_returns_invalid_token_for_non_match(monkeypatch) -> None:
    """Non-matching token should map to invalid_token decision."""
    monkeypatch.setenv("BGPX_ADMIN_TOKENS", "token_a|person a;token_b|person b")

    result = validate_admin_token("token_c")

    assert result.is_authorized is False
    assert result.reason == "invalid_token"
    assert result.matched_note is None


def test_validate_admin_token_returns_ok_and_note_for_match(monkeypatch) -> None:
    """Matching token should authorize and include matched note metadata."""
    monkeypatch.setenv("BGPX_ADMIN_TOKENS", "token_a|person a;token_b|person b")

    result = validate_admin_token("token_b")

    assert result.is_authorized is True
    assert result.reason == "ok"
    assert result.matched_note == "person b"


def test_get_admin_token_auth_config_state_reflects_configured_state(monkeypatch) -> None:
    """Config-state helper should expose configured flag and token count."""
    monkeypatch.setenv("BGPX_ADMIN_TOKENS", "token_a|person a;token_b")

    state = get_admin_token_auth_config_state()

    assert state.is_configured is True
    assert state.configured_token_count == 2


def test_require_admin_token_raises_401_when_config_missing(monkeypatch) -> None:
    """Guard should map missing config to consistent 401 response."""
    monkeypatch.delenv("BGPX_ADMIN_TOKENS", raising=False)

    with pytest.raises(HTTPException) as exc_info:
        require_admin_token("token_a")

    exc = exc_info.value
    assert getattr(exc, "status_code", None) == 401
    assert getattr(exc, "detail", None) == "Admin token authentication is not configured"


def test_require_admin_token_raises_401_when_token_missing(monkeypatch) -> None:
    """Guard should map missing token to consistent 401 response."""
    monkeypatch.setenv("BGPX_ADMIN_TOKENS", "token_a|person a")

    with pytest.raises(HTTPException) as exc_info:
        require_admin_token(None)

    exc = exc_info.value
    assert getattr(exc, "status_code", None) == 401
    assert getattr(exc, "detail", None) == "Missing X-Admin-Token header"


def test_require_admin_token_raises_401_when_token_invalid(monkeypatch) -> None:
    """Guard should map invalid token to consistent 401 response."""
    monkeypatch.setenv("BGPX_ADMIN_TOKENS", "token_a|person a")

    with pytest.raises(HTTPException) as exc_info:
        require_admin_token("invalid")

    exc = exc_info.value
    assert getattr(exc, "status_code", None) == 401
    assert getattr(exc, "detail", None) == "Invalid admin token"


def test_require_admin_token_returns_validation_result_when_token_valid(monkeypatch) -> None:
    """Guard should return validation metadata when request is authorized."""
    monkeypatch.setenv("BGPX_ADMIN_TOKENS", "token_a|person a;token_b|person b")

    result = require_admin_token("token_b")

    assert result.is_authorized is True
    assert result.reason == "ok"
    assert result.matched_note == "person b"
