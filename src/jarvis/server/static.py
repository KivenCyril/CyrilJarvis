"""Static file serving for the JARVIS web frontend."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

WEB_DIR = Path(__file__).resolve().parents[3] / "web"


def mount_static(app: FastAPI) -> None:
    """Mount the web frontend as static files if the directory exists."""
    if not WEB_DIR.exists():
        return

    @app.get("/")
    async def serve_frontend():
        return FileResponse(WEB_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")
