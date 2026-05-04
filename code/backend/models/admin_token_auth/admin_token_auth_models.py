"""Shared models for admin token authentication contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


AdminTokenValidationReason = Literal[
    "ok",
    "missing_config",
    "missing_token",
    "invalid_token",
]


@dataclass(frozen=True)
class AdminTokenValidationResultModel:
    """Service-level authorization decision and deterministic reason metadata."""

    is_authorized: bool
    reason: AdminTokenValidationReason
    matched_note: str | None = None

    def __post_init__(self) -> None:
        """Validate consistency between authorization status and reason."""
        if self.is_authorized and self.reason != "ok":
            raise ValueError("reason must be 'ok' when is_authorized is True")

        if not self.is_authorized and self.reason == "ok":
            raise ValueError("reason cannot be 'ok' when is_authorized is False")

        if self.matched_note is not None and not self.matched_note.strip():
            raise ValueError("matched_note must be a non-empty string when provided")


@dataclass(frozen=True)
class AdminAuthErrorModel:
    """Stable, user-safe authentication error payload contract."""

    code: str
    message: str

    def __post_init__(self) -> None:
        """Validate error contract fields."""
        if not self.code.strip():
            raise ValueError("code must be a non-empty string")

        if not self.message.strip():
            raise ValueError("message must be a non-empty string")


@dataclass(frozen=True)
class AdminTokenAuthConfigStateModel:
    """Auth configuration observability state for configured token inventory."""

    is_configured: bool
    configured_token_count: int = 0

    def __post_init__(self) -> None:
        """Validate non-negative configured token counter."""
        if self.configured_token_count < 0:
            raise ValueError("configured_token_count cannot be negative")


__all__ = [
    "AdminAuthErrorModel",
    "AdminTokenAuthConfigStateModel",
    "AdminTokenValidationReason",
    "AdminTokenValidationResultModel",
]
