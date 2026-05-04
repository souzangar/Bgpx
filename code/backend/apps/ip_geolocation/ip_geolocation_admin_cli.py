"""Admin-only CLI for IP geolocation operational actions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

try:
    from .ip_geolocation_app import (
        get_ip_geolocation_load_status,
        get_ip_geolocation_service,
        lookup_ip_geolocation,
    )
except ImportError:  # direct script execution fallback
    BACKEND_DIR = Path(__file__).resolve().parents[2]
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    from apps.ip_geolocation.ip_geolocation_app import (  # type: ignore
        get_ip_geolocation_load_status,
        get_ip_geolocation_service,
        lookup_ip_geolocation,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ip-geolocation-admin")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("reinitialize", help="Reset service runtime state to loading")
    subparsers.add_parser("status", help="Show current IP geolocation load status")

    lookup_parser = subparsers.add_parser("lookup", help="Run one lookup for diagnostics")
    lookup_parser.add_argument("--ip", required=True, help="Target IP address")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Execute IP geolocation admin CLI command."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "reinitialize":
        get_ip_geolocation_service().initialize_ip_geolocation_dataset()
        print("reinitialized")
        return 0

    if args.command == "status":
        status = get_ip_geolocation_load_status()
        print(
            json.dumps(
                {
                    "service_state": status.service_state,
                    "counters": {
                        "total": status.counters.total,
                        "loaded": status.counters.loaded,
                        "malformed": status.counters.malformed,
                    },
                    "last_loaded_at": status.last_loaded_at.isoformat() if status.last_loaded_at else None,
                }
            )
        )
        return 0

    if args.command == "lookup":
        payload = lookup_ip_geolocation(args.ip)
        if payload.status == "failure":
            print(
                json.dumps(
                    {
                        "status": payload.status,
                        "service_state": payload.service_state,
                        "error": {
                            "code": payload.error.code,
                            "message": payload.error.message,
                        },
                    }
                )
            )
            return 0

        print(
            json.dumps(
                {
                    "status": payload.status,
                    "service_state": payload.service_state,
                    "resolution_state": payload.resolution_state,
                    "data": {
                        "ip": payload.data.ip,
                        "network": payload.data.network,
                        "country": payload.data.country,
                        "country_code": payload.data.country_code,
                        "continent": payload.data.continent,
                        "continent_code": payload.data.continent_code,
                        "asn": payload.data.asn,
                        "as_name": payload.data.as_name,
                        "as_domain": payload.data.as_domain,
                    },
                }
            )
        )
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())


# -----------------------------------------------------------------------------
# Wiring Notes (post `admin_token_auth` implementation)
# -----------------------------------------------------------------------------
# This CLI currently contains local-process operational helpers for IP geo.
# For runtime-integrated admin operations, this CLI should be wired as an HTTP
# client to the running backend process (single source of truth for in-memory
# service/refresher state).
#
# Planned wiring contract:
# 1) Token/Auth
#    - Token source env: `BGPX_ADMIN_TOKEN`
#    - Header: `X-Admin-Token`
#    - CLI token resolution order:
#      a) explicit CLI arg (e.g. `--token`)
#      b) fallback to `BGPX_ADMIN_TOKEN`
#
# 2) Endpoint mapping
#    - `status`       -> GET  /api/admin/ip-geolocation/status
#    - `reinitialize` -> POST /api/admin/ip-geolocation/reinitialize
#    - `refresh-once` -> POST /api/admin/ip-geolocation/refresh-once
#    - optional diag lookup -> GET /api/admin/ip-geolocation/lookup?ip=...
#
# 3) Runtime expectation
#    - CLI must operate against an already running backend instance.
#    - CLI process should not be considered authoritative runtime state.
#
# 4) Failure behavior
#    - 401 -> missing/invalid admin token
#    - connection error -> backend not reachable / wrong base URL
#    - never log raw admin token values
#
# 5) Reuse pattern
#    - same token-guarded admin-CLI pattern should be reused for future
#      private admin operations in other domains.
