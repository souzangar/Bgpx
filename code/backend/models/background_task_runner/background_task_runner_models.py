"""Shared models for background task runner contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Awaitable, Callable, TypeAlias


SyncTaskCallable: TypeAlias = Callable[[], None]
AsyncTaskCallable: TypeAlias = Callable[[], Awaitable[None]]
TaskCallable: TypeAlias = SyncTaskCallable | AsyncTaskCallable


class OverlapPolicy(str, Enum):
    """Execution policy for handling overlapping task runs."""

    SKIP_IF_RUNNING = "SKIP_IF_RUNNING"
    QUEUE_ONE = "QUEUE_ONE"
    RESTART = "RESTART"


@dataclass
class RetryBackoffConfig:
    """Retry and backoff configuration for per-task failure handling."""

    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 10.0
    jitter_ratio: float = 0.2

    def __post_init__(self) -> None:
        """Validate retry/backoff configuration boundaries."""
        if self.base_delay_seconds <= 0:
            raise ValueError("base_delay_seconds must be greater than 0")

        if self.max_delay_seconds <= 0:
            raise ValueError("max_delay_seconds must be greater than 0")

        if self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError("max_delay_seconds must be >= base_delay_seconds")

        if not 0 <= self.jitter_ratio <= 1:
            raise ValueError("jitter_ratio must be in range [0, 1]")


@dataclass
class BackgroundTaskDefinition:
    """Contract used to register a background task in the runner."""

    task_id: str
    interval_seconds: float
    run_once: TaskCallable
    overlap_policy: OverlapPolicy = OverlapPolicy.SKIP_IF_RUNNING
    retry_backoff: RetryBackoffConfig = field(default_factory=RetryBackoffConfig)

    def __post_init__(self) -> None:
        """Validate registration contract values."""
        if not self.task_id.strip():
            raise ValueError("task_id must be a non-empty string")

        if self.interval_seconds <= 0:
            raise ValueError("interval_seconds must be greater than 0")

        if not callable(self.run_once):
            raise ValueError("run_once must be callable")


@dataclass
class BackgroundTaskStatus:
    """Observable runtime metadata for a registered background task."""

    task_id: str
    is_running: bool = False
    last_run_started_at: datetime | None = None
    last_run_succeeded_at: datetime | None = None
    last_error_message: str | None = None
    consecutive_failure_count: int = 0
    total_runs: int = 0
    skipped_overlap_runs: int = 0

    def __post_init__(self) -> None:
        """Validate status object consistency."""
        if not self.task_id.strip():
            raise ValueError("task_id must be a non-empty string")

        if self.consecutive_failure_count < 0:
            raise ValueError("consecutive_failure_count cannot be negative")

        if self.total_runs < 0:
            raise ValueError("total_runs cannot be negative")

        if self.skipped_overlap_runs < 0:
            raise ValueError("skipped_overlap_runs cannot be negative")


__all__ = [
    "AsyncTaskCallable",
    "BackgroundTaskDefinition",
    "BackgroundTaskStatus",
    "OverlapPolicy",
    "RetryBackoffConfig",
    "SyncTaskCallable",
    "TaskCallable",
]
