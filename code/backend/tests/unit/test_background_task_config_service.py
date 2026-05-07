"""Unit tests for background task JSON configuration service."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest


BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.background_task_runner import background_task_config_service as config_service  # noqa: E402


def test_get_background_tasks_config_returns_valid_ip_geo_defaults() -> None:
    """Default repository config should parse into expected task keys/ids."""
    config_service.reset_background_task_config_cache_for_tests()
    try:
        config = config_service.get_background_tasks_config()
        assert config.version == 1
        assert config.ip_geolocation.resource_key == "ip_geolocation_database_handler"

        task_by_key = {task.task_key: task for task in config.ip_geolocation.tasks}
        assert task_by_key["bootstrap_once"].task_id == "ip_geolocation_bootstrap_once"
        assert task_by_key["ipinfo_gz_downloader"].task_id == "ip_geolocation_ipinfo_gz_downloader"
        assert task_by_key["data_refresh"].task_id == "ip_geolocation_data_refresh"
    finally:
        config_service.reset_background_task_config_cache_for_tests()


def test_get_background_tasks_config_uses_cache_when_mtime_unchanged() -> None:
    """When mtime is unchanged, service should return same cached object instance."""
    config_service.reset_background_task_config_cache_for_tests()
    try:
        first = config_service.get_background_tasks_config()
        second = config_service.get_background_tasks_config()
        assert second is first
    finally:
        config_service.reset_background_task_config_cache_for_tests()


def test_get_background_tasks_config_reloads_when_file_mtime_changes(tmp_path: Path) -> None:
    """Service should re-parse config when backing file mtime changes."""
    original_path = config_service.BACKGROUND_TASK_CONFIG_PATH
    config_service.reset_background_task_config_cache_for_tests()

    first_payload = {
        "version": 1,
        "ip_geolocation": {
            "resource_key": "rk-a",
            "tasks": {
                "bootstrap_once": {
                    "task_id": "t-bootstrap",
                    "interval_seconds": 1.0,
                    "resource_sequence": 5,
                    "enabled": True,
                    "stop_after_success": True,
                },
                "ipinfo_gz_downloader": {
                    "task_id": "t-download",
                    "interval_seconds": 2.0,
                    "resource_sequence": 10,
                    "enabled": True,
                },
                "data_refresh": {
                    "task_id": "t-refresh",
                    "interval_seconds": 3.0,
                    "resource_sequence": 20,
                    "enabled": True,
                },
            },
        },
    }
    second_payload = {
        "version": 1,
        "ip_geolocation": {
            "resource_key": "rk-b",
            "tasks": {
                "bootstrap_once": {
                    "task_id": "t-bootstrap-2",
                    "interval_seconds": 1.5,
                    "resource_sequence": 5,
                    "enabled": True,
                    "stop_after_success": True,
                },
                "ipinfo_gz_downloader": {
                    "task_id": "t-download-2",
                    "interval_seconds": 2.5,
                    "resource_sequence": 10,
                    "enabled": True,
                },
                "data_refresh": {
                    "task_id": "t-refresh-2",
                    "interval_seconds": 3.5,
                    "resource_sequence": 20,
                    "enabled": True,
                },
            },
        },
    }

    config_path = tmp_path / "background_tasks_config.json"
    config_path.write_text(json.dumps(first_payload), encoding="utf-8")

    try:
        config_service.BACKGROUND_TASK_CONFIG_PATH = config_path
        first = config_service.get_background_tasks_config()
        assert first.ip_geolocation.resource_key == "rk-a"

        config_path.write_text(json.dumps(second_payload), encoding="utf-8")
        third = config_service.get_background_tasks_config()
        assert third.ip_geolocation.resource_key == "rk-b"
        assert third is not first
    finally:
        config_service.BACKGROUND_TASK_CONFIG_PATH = original_path
        config_service.reset_background_task_config_cache_for_tests()


def test_get_background_tasks_config_raises_on_invalid_payload(tmp_path: Path) -> None:
    """Invalid config shape should fail fast with clear runtime error."""
    original_path = config_service.BACKGROUND_TASK_CONFIG_PATH
    config_service.reset_background_task_config_cache_for_tests()

    invalid_payload = {
        "version": 1,
        "ip_geolocation": {
            "resource_key": "rk",
            "tasks": {
                "bootstrap_once": {
                    "task_id": "dup",
                    "interval_seconds": 1.0,
                    "resource_sequence": 5,
                    "enabled": True,
                },
                "ipinfo_gz_downloader": {
                    "task_id": "dup",
                    "interval_seconds": 2.0,
                    "resource_sequence": 10,
                    "enabled": True,
                },
                "data_refresh": {
                    "task_id": "refresh",
                    "interval_seconds": 3.0,
                    "resource_sequence": 20,
                    "enabled": True,
                },
            },
        },
    }
    config_path = tmp_path / "background_tasks_config.json"
    config_path.write_text(json.dumps(invalid_payload), encoding="utf-8")

    try:
        config_service.BACKGROUND_TASK_CONFIG_PATH = config_path
        with pytest.raises(RuntimeError, match="duplicate task_id"):
            config_service.get_background_tasks_config()
    finally:
        config_service.BACKGROUND_TASK_CONFIG_PATH = original_path
        config_service.reset_background_task_config_cache_for_tests()
