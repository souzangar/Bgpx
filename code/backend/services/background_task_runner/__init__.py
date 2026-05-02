"""Background task runner service package.

This package hosts reusable, domain-agnostic background task runtime
orchestration utilities for the backend services layer.

Shared task contracts and DTOs are owned by ``models.background_task_runner``.
"""

from models.background_task_runner import (  # noqa: F401
    AsyncTaskCallable,
    BackgroundTaskDefinition,
    BackgroundTaskStatus,
    OverlapPolicy,
    RetryBackoffConfig,
    SyncTaskCallable,
    TaskCallable,
)
from .background_task_runner import (  # noqa: F401
    BackgroundTaskRunner,
    get_background_task_runner,
    reset_background_task_runner_for_tests,
)

__all__ = [
    "AsyncTaskCallable",
    "BackgroundTaskRunner",
    "BackgroundTaskDefinition",
    "BackgroundTaskStatus",
    "get_background_task_runner",
    "OverlapPolicy",
    "reset_background_task_runner_for_tests",
    "RetryBackoffConfig",
    "SyncTaskCallable",
    "TaskCallable",
]
