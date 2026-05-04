"""Initial FastAPI entrypoint for the BGPX backend."""

from __future__ import annotations

import argparse
from contextlib import asynccontextmanager
import os
from pathlib import Path
import socket
import subprocess
import time
from urllib.parse import urlparse

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from api import router as api_router
from apps.ip_geolocation import get_ip_geolocation_service
from models.background_task_runner import BackgroundTaskDefinition
from services.background_task_runner import get_background_task_runner
from services.ip_geolocation.ip_geolocation_data_refresher import IpGeolocationDataRefresher
from services.sslCert import ensure_ssl_files


FRONTEND_MODE_ENV = "BGPX_FRONTEND_MODE"
FRONTEND_DEV_URL_ENV = "BGPX_FRONTEND_DEV_URL"
VERBOSE_ENV = "BGPX_VERBOSE"
DEFAULT_FRONTEND_DEV_URL = "https://localhost:5173"
FRONTEND_STARTUP_TIMEOUT_SECONDS = 30.0
IP_GEO_REFRESH_TASK_ID = "ip_geolocation_source_watch"
IP_GEO_REFRESH_INTERVAL_SECONDS = 1.0


def _resolve_frontend_mode(explicit_mode: str | None = None) -> str:
    """Resolve frontend mode from explicit value or environment."""
    mode = (explicit_mode or os.getenv(FRONTEND_MODE_ENV, "dist")).strip().lower()
    return mode if mode in {"dist", "dev"} else "dist"


def _resolve_frontend_dev_url(explicit_url: str | None = None) -> str:
    """Resolve frontend development server URL."""
    url = (explicit_url or os.getenv(FRONTEND_DEV_URL_ENV, DEFAULT_FRONTEND_DEV_URL)).strip()
    return url.rstrip("/") or DEFAULT_FRONTEND_DEV_URL


def _extract_host_port(url: str) -> tuple[str, int]:
    """Extract host and port from a frontend URL."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(
            f"Invalid frontend dev URL '{url}'. Expected format like https://localhost:5173"
        )

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return parsed.hostname, port


def _is_tcp_open(host: str, port: int, timeout: float = 0.3) -> bool:
    """Check whether a TCP host:port is reachable."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _wait_for_tcp(host: str, port: int, timeout_seconds: float) -> None:
    """Wait until a TCP endpoint becomes reachable."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if _is_tcp_open(host, port):
            return
        time.sleep(0.25)

    raise TimeoutError(f"Timed out waiting for frontend dev server at {host}:{port}")


def _stop_subprocess(process: subprocess.Popen | None) -> None:
    """Terminate a subprocess gracefully when possible."""
    if process is None or process.poll() is not None:
        return

    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def _is_api_path(full_path: str) -> bool:
    """Return True when the requested catch-all path targets API routes."""
    return full_path == "api" or full_path.startswith("api/")


def _is_assets_path(full_path: str) -> bool:
    """Return True when the requested catch-all path targets asset routes."""
    return full_path == "assets" or full_path.startswith("assets/")


def _build_dev_redirect_target(base_url: str, full_path: str, query: str) -> str:
    """Build redirect target URL for frontend development mode."""
    target = f"{base_url}/{full_path.lstrip('/')}" if full_path else f"{base_url}/"
    if query:
        return f"{target}?{query}"
    return target


def _ensure_not_found(condition: bool, detail: str = "Not Found") -> None:
    """Raise an HTTP 404 when condition is true."""
    if condition:
        raise HTTPException(status_code=404, detail=detail)


def _serve_frontend_index(frontend_dist: Path) -> FileResponse:
    """Serve built frontend index.html or raise when dist output is missing."""
    index_file = frontend_dist / "index.html"
    if not index_file.exists():
        raise HTTPException(
            status_code=404,
            detail="Frontend build not found. Run npm run build in code/frontend.",
        )

    return FileResponse(index_file)


def _start_frontend_dev_server(frontend_dev_url: str, frontend_dir: Path) -> subprocess.Popen | None:
    """Start Vite dev server for single-terminal development mode."""
    host, port = _extract_host_port(frontend_dev_url)

    if _is_tcp_open(host, port):
        print(f"Frontend dev server already running at {frontend_dev_url}")
        return None

    if not frontend_dir.exists():
        raise RuntimeError(f"Frontend directory not found: {frontend_dir}")

    command = [
        "npm",
        "run",
        "dev",
        "--",
        "--host",
        host,
        "--port",
        str(port),
        "--strictPort",
    ]

    process = subprocess.Popen(command, cwd=frontend_dir)

    try:
        _wait_for_tcp(host, port, FRONTEND_STARTUP_TIMEOUT_SECONDS)
    except Exception as exc:
        _stop_subprocess(process)
        raise RuntimeError(
            f"Could not start frontend dev server at {frontend_dev_url}. "
            "Check npm dependencies in code/frontend and available port."
        ) from exc

    print(f"Frontend dev server started at {frontend_dev_url}")
    return process


@asynccontextmanager
async def _app_lifespan(_app: FastAPI):
    """Manage process-local shared services bound to FastAPI lifecycle."""
    runner = get_background_task_runner()
    runner.start_background_task_runner()

    ip_geolocation_service = get_ip_geolocation_service()
    ip_geolocation_service.initialize_ip_geolocation_dataset()
    ip_geolocation_refresher = IpGeolocationDataRefresher(
        publish_snapshot=ip_geolocation_service.publish_snapshot,
    )

    ip_geo_refresh_task = BackgroundTaskDefinition(
        task_id=IP_GEO_REFRESH_TASK_ID,
        interval_seconds=IP_GEO_REFRESH_INTERVAL_SECONDS,
        run_once=ip_geolocation_refresher.run_once,
    )

    try:
        runner.register_background_task(ip_geo_refresh_task)
    except ValueError:
        # Task already registered in this process; keep lifecycle idempotent.
        pass

    runner.start_background_task(IP_GEO_REFRESH_TASK_ID)

    try:
        yield
    finally:
        try:
            runner.stop_background_task(IP_GEO_REFRESH_TASK_ID)
        except KeyError:
            pass

        try:
            runner.unregister_background_task(IP_GEO_REFRESH_TASK_ID)
        except KeyError:
            pass

        runner.stop_background_task_runner()


def create_app(frontend_mode: str | None = None, frontend_dev_url: str | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="BGPX Backend", version="0.1.0", lifespan=_app_lifespan)
    app.include_router(api_router, prefix="/api")

    backend_dir = Path(__file__).resolve().parent
    frontend_dist = backend_dir.parent / "frontend" / "dist"
    assets_dir = frontend_dist / "assets"

    resolved_frontend_mode = _resolve_frontend_mode(frontend_mode)
    resolved_frontend_dev_url = _resolve_frontend_dev_url(frontend_dev_url)

    if resolved_frontend_mode == "dist" and assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")

    @app.get(
        "/{full_path:path}",
        include_in_schema=False,
        responses={404: {"description": "Not Found"}},
    )
    def serve_frontend(full_path: str, request: Request) -> Response:
        """Serve SPA routes from build output or redirect to Vite dev server."""
        _ensure_not_found(_is_api_path(full_path))

        if resolved_frontend_mode == "dev":
            target = _build_dev_redirect_target(
                resolved_frontend_dev_url,
                full_path,
                request.url.query,
            )
            return RedirectResponse(url=target, status_code=307)

        _ensure_not_found(_is_assets_path(full_path))
        return _serve_frontend_index(frontend_dist)

    return app


app = create_app()


def parse_args() -> argparse.Namespace:
    """Parse runtime CLI flags."""
    parser = argparse.ArgumentParser(description="Run BGPX backend API.")
    parser.add_argument(
        "-dev",
        "--dev",
        action="store_true",
        help="Enable frontend development mode (auto-starts Vite and redirects non-API routes).",
    )
    parser.add_argument(
        "--frontend-dev-url",
        default=os.getenv(FRONTEND_DEV_URL_ENV, DEFAULT_FRONTEND_DEV_URL),
        help=f"Frontend dev server URL used with -dev (default: {DEFAULT_FRONTEND_DEV_URL}).",
    )
    parser.add_argument(
        "-verbose",
        action="store_true",
        help="Enable verbose backend logging (includes Uvicorn access logs).",
    )
    return parser.parse_args()


def main() -> None:
    """Run the backend with Uvicorn over HTTPS."""
    args = parse_args()
    frontend_process: subprocess.Popen | None = None
    ssl_files = ensure_ssl_files()
    os.environ[VERBOSE_ENV] = "1" if args.verbose else "0"

    if args.dev:
        os.environ[FRONTEND_MODE_ENV] = "dev"
        os.environ[FRONTEND_DEV_URL_ENV] = args.frontend_dev_url

        backend_dir = Path(__file__).resolve().parent
        frontend_dir = backend_dir.parent / "frontend"
        frontend_process = _start_frontend_dev_server(args.frontend_dev_url, frontend_dir)

    backend_dir = Path(__file__).resolve().parent
    host = os.getenv("BGPX_HOST", "0.0.0.0")
    port = int(os.getenv("BGPX_PORT", "443"))

    try:
        uvicorn.run(
            "main:create_app",
            factory=True,
            host=host,
            port=port,
            ssl_certfile=str(ssl_files.cert_file),
            ssl_keyfile=str(ssl_files.key_file),
            reload=True,
            reload_dirs=[str(backend_dir)],
            access_log=args.verbose,
        )
    finally:
        _stop_subprocess(frontend_process)


if __name__ == "__main__":
    main()
