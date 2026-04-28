"""Initial FastAPI entrypoint for the BGPX backend."""

from __future__ import annotations

import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api import router as api_router
from services.sslCert_service import ensure_ssl_files


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="BGPX Backend", version="0.1.0")
    app.include_router(api_router, prefix="/api")

    backend_dir = Path(__file__).resolve().parent
    frontend_dist = backend_dir.parent / "frontend" / "dist"
    assets_dir = frontend_dist / "assets"

    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_frontend(full_path: str) -> FileResponse:
        """Serve SPA shell for non-API routes from frontend build output."""
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")

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
