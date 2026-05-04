"""Unit tests for IP geolocation admin CLI behavior."""

from __future__ import annotations

from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from apps.ip_geolocation.ip_geolocation_admin_cli import main


def test_cli_reinitialize_calls_service_and_returns_zero(monkeypatch, capsys) -> None:
    """reinitialize command should delegate to service init and print confirmation."""
    called = {"value": False}

    class _FakeService:
        def initialize_ip_geolocation_dataset(self) -> None:
            called["value"] = True

    monkeypatch.setattr(
        "apps.ip_geolocation.ip_geolocation_admin_cli.get_ip_geolocation_service",
        lambda: _FakeService(),
    )

    exit_code = main(["reinitialize"])

    assert exit_code == 0
    assert called["value"] is True
    assert "reinitialized" in capsys.readouterr().out


def test_cli_status_prints_json(monkeypatch, capsys) -> None:
    """status command should print serialized status json."""
    from models.ip_geolocation import IpGeolocationLoadCountersModel, IpGeolocationLoadStatusModel

    monkeypatch.setattr(
        "apps.ip_geolocation.ip_geolocation_admin_cli.get_ip_geolocation_load_status",
        lambda: IpGeolocationLoadStatusModel(
            service_state="ready",
            counters=IpGeolocationLoadCountersModel(total=2, loaded=2, malformed=0),
        ),
    )

    exit_code = main(["status"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert '"service_state": "ready"' in output


def test_cli_lookup_prints_success_json(monkeypatch, capsys) -> None:
    """lookup command should print lookup payload json for success envelope."""
    from models.ip_geolocation import IpGeolocationLookupDataModel, IpGeolocationLookupSuccessResponseModel

    monkeypatch.setattr(
        "apps.ip_geolocation.ip_geolocation_admin_cli.lookup_ip_geolocation",
        lambda _ip: IpGeolocationLookupSuccessResponseModel(
            status="success",
            service_state="ready",
            resolution_state="not_found",
            data=IpGeolocationLookupDataModel(
                ip="9.9.9.9",
                network=None,
                country=None,
                country_code=None,
                continent=None,
                continent_code=None,
                asn=None,
                as_name=None,
                as_domain=None,
            ),
        ),
    )

    exit_code = main(["lookup", "--ip", "9.9.9.9"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert '"resolution_state": "not_found"' in output
