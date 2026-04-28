"""Initial FastAPI entrypoint for the BGPX backend."""

from __future__ import annotations

import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from api import router as api_router
from services.sslCert_service import ensure_ssl_files


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="BGPX Backend", version="0.1.0")
    app.include_router(api_router, prefix="/api")
    return app


app = create_app()


def main() -> None:
    """Run the backend with Uvicorn over HTTPS."""
    ssl_files = ensure_ssl_files()
    backend_dir = Path(__file__).resolve().parent
    host = os.getenv("BGPX_HOST", "0.0.0.0")
    port = int(os.getenv("BGPX_PORT", "443"))

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        ssl_certfile=str(ssl_files.cert_file),
        ssl_keyfile=str(ssl_files.key_file),
        reload=True,
        reload_dirs=[str(backend_dir)],
    )


if __name__ == "__main__":
    main()
