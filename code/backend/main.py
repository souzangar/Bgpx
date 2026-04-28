"""Initial FastAPI entrypoint for the BGPX backend."""

from __future__ import annotations

import argparse
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
from services.sslCert_service import ensure_ssl_files


FRONTEND_MODE_ENV = "BGPX_FRONTEND_MODE"
FRONTEND_DEV_URL_ENV = "BGPX_FRONTEND_DEV_URL"
DEFAULT_FRONTEND_DEV_URL = "http://localhost:5173"
FRONTEND_STARTUP_TIMEOUT_SECONDS = 30.0


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
            f"Invalid frontend dev URL '{url}'. Expected format like http://localhost:5173"
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


def create_app(frontend_mode: str | None = None, frontend_dev_url: str | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="BGPX Backend", version="0.1.0")
    app.include_router(api_router, prefix="/api")

    backend_dir = Path(__file__).resolve().parent
    frontend_dist = backend_dir.parent / "frontend" / "dist"
    assets_dir = frontend_dist / "assets"

    resolved_frontend_mode = _resolve_frontend_mode(frontend_mode)
    resolved_frontend_dev_url = _resolve_frontend_dev_url(frontend_dev_url)

    if resolved_frontend_mode == "dist" and assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_frontend(full_path: str, request: Request) -> Response:
        """Serve SPA routes from build output or redirect to Vite dev server."""
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")

        if resolved_frontend_mode == "dev":
            target = (
                f"{resolved_frontend_dev_url}/{full_path.lstrip('/')}"
                if full_path
                else f"{resolved_frontend_dev_url}/"
            )
            if request.url.query:
                target = f"{target}?{request.url.query}"
            return RedirectResponse(url=target, status_code=307)

        if full_path == "assets" or full_path.startswith("assets/"):
            raise HTTPException(status_code=404, detail="Not Found")

        index_file = frontend_dist / "index.html"
        if not index_file.exists():
            raise HTTPException(
                status_code=404,
                detail="Frontend build not found. Run npm run build in code/frontend.",
            )

        return FileResponse(index_file)

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
    return parser.parse_args()


def main() -> None:
    """Run the backend with Uvicorn over HTTPS."""
    args = parse_args()
    frontend_process: subprocess.Popen | None = None

    if args.dev:
        os.environ[FRONTEND_MODE_ENV] = "dev"
        os.environ[FRONTEND_DEV_URL_ENV] = args.frontend_dev_url

        backend_dir = Path(__file__).resolve().parent
        frontend_dir = backend_dir.parent / "frontend"
        frontend_process = _start_frontend_dev_server(args.frontend_dev_url, frontend_dir)

    ssl_files = ensure_ssl_files()
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
        )
    finally:
        _stop_subprocess(frontend_process)


if __name__ == "__main__":
    main()
