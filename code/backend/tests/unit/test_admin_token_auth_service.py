"""Unit tests for admin token auth service parsing and validation behavior."""

from __future__ import annotations

from pathlib import Path
import json
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
    reset_admin_token_auth_config_cache_for_tests,
    validate_admin_token,
)


def _write_admin_token_config(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "admin_token_auth_config.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _use_config_path(monkeypatch, config_path: Path) -> None:
    monkeypatch.setattr(
        "services.admin_token_auth.admin_token_auth_service.ADMIN_TOKEN_AUTH_CONFIG_PATH",
        config_path,
    )
    reset_admin_token_auth_config_cache_for_tests()


def test_get_configured_admin_tokens_deduplicates_and_retains_first_note(monkeypatch, tmp_path: Path) -> None:
    """Parser should validate JSON token entries and de-duplicate by first token occurrence."""
    config_path = _write_admin_token_config(
        tmp_path,
        {
            "version": 1,
            "tokens": [
                {"token": " token_a ", "note": " person a "},
                {"token": "token_b", "note": "person b"},
                {"token": "token_a", "note": "duplicate note"},
                {"token": "token_c"},
            ],
        },
    )
    _use_config_path(monkeypatch, config_path)

    entries = get_configured_admin_tokens()

    assert len(entries) == 3
    assert entries[0] == ("token_a", "person a")
    assert entries[1] == ("token_b", "person b")
    assert entries[2] == ("token_c", None)


def test_validate_admin_token_returns_missing_config_when_file_missing(monkeypatch, tmp_path: Path) -> None:
    """Validation should fail-closed when config file is missing."""
    _use_config_path(monkeypatch, tmp_path / "does_not_exist.json")

    result = validate_admin_token("token_a")

    assert result.is_authorized is False
    assert result.reason == "missing_config"
    assert result.matched_note is None


def test_validate_admin_token_returns_missing_token_when_request_token_absent(monkeypatch, tmp_path: Path) -> None:
    """Configured tokens with absent provided token should return missing_token."""
    config_path = _write_admin_token_config(
        tmp_path,
        {"version": 1, "tokens": [{"token": "token_a", "note": "person a"}]},
    )
    _use_config_path(monkeypatch, config_path)

    result = validate_admin_token(None)

    assert result.is_authorized is False
    assert result.reason == "missing_token"
    assert result.matched_note is None


def test_validate_admin_token_returns_invalid_token_for_non_match(monkeypatch, tmp_path: Path) -> None:
    """Non-matching token should map to invalid_token decision."""
    config_path = _write_admin_token_config(
        tmp_path,
        {
            "version": 1,
            "tokens": [{"token": "token_a", "note": "person a"}, {"token": "token_b", "note": "person b"}],
        },
    )
    _use_config_path(monkeypatch, config_path)

    result = validate_admin_token("token_c")

    assert result.is_authorized is False
    assert result.reason == "invalid_token"
    assert result.matched_note is None


def test_validate_admin_token_returns_ok_and_note_for_match(monkeypatch, tmp_path: Path) -> None:
    """Matching token should authorize and include matched note metadata."""
    config_path = _write_admin_token_config(
        tmp_path,
        {
            "version": 1,
            "tokens": [{"token": "token_a", "note": "person a"}, {"token": "token_b", "note": "person b"}],
        },
    )
    _use_config_path(monkeypatch, config_path)

    result = validate_admin_token("token_b")

    assert result.is_authorized is True
    assert result.reason == "ok"
    assert result.matched_note == "person b"


def test_get_admin_token_auth_config_state_reflects_configured_state(monkeypatch, tmp_path: Path) -> None:
    """Config-state helper should expose configured flag and token count."""
    config_path = _write_admin_token_config(
        tmp_path,
        {"version": 1, "tokens": [{"token": "token_a", "note": "person a"}, {"token": "token_b"}]},
    )
    _use_config_path(monkeypatch, config_path)

    state = get_admin_token_auth_config_state()

    assert state.is_configured is True
    assert state.configured_token_count == 2


def test_require_admin_token_raises_401_when_config_missing(monkeypatch, tmp_path: Path) -> None:
    """Guard should map missing config to consistent 401 response."""
    _use_config_path(monkeypatch, tmp_path / "does_not_exist.json")

    with pytest.raises(HTTPException) as exc_info:
        require_admin_token("token_a")

    exc = exc_info.value
    assert getattr(exc, "status_code", None) == 401
    assert getattr(exc, "detail", None) == "Admin token authentication is not configured"


def test_require_admin_token_raises_401_when_token_missing(monkeypatch, tmp_path: Path) -> None:
    """Guard should map missing token to consistent 401 response."""
    config_path = _write_admin_token_config(
        tmp_path,
        {"version": 1, "tokens": [{"token": "token_a", "note": "person a"}]},
    )
    _use_config_path(monkeypatch, config_path)

    with pytest.raises(HTTPException) as exc_info:
        require_admin_token(None)

    exc = exc_info.value
    assert getattr(exc, "status_code", None) == 401
    assert getattr(exc, "detail", None) == "Missing X-Admin-Token header"


def test_require_admin_token_raises_401_when_token_invalid(monkeypatch, tmp_path: Path) -> None:
    """Guard should map invalid token to consistent 401 response."""
    config_path = _write_admin_token_config(
        tmp_path,
        {"version": 1, "tokens": [{"token": "token_a", "note": "person a"}]},
    )
    _use_config_path(monkeypatch, config_path)

    with pytest.raises(HTTPException) as exc_info:
        require_admin_token("invalid")

    exc = exc_info.value
    assert getattr(exc, "status_code", None) == 401
    assert getattr(exc, "detail", None) == "Invalid admin token"


def test_require_admin_token_returns_validation_result_when_token_valid(monkeypatch, tmp_path: Path) -> None:
    """Guard should return validation metadata when request is authorized."""
    config_path = _write_admin_token_config(
        tmp_path,
        {
            "version": 1,
            "tokens": [{"token": "token_a", "note": "person a"}, {"token": "token_b", "note": "person b"}],
        },
    )
    _use_config_path(monkeypatch, config_path)

    result = require_admin_token("token_b")

    assert result.is_authorized is True
    assert result.reason == "ok"
    assert result.matched_note == "person b"
