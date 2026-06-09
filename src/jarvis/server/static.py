"""Static file serving for the JARVIS web frontend."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


WEB_DIR = Path(__file__).resolve().parents[3] / "web"


class NoCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith("/web"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response


def mount_static(app: FastAPI) -> None:
    """Mount the web frontend as static files if the directory exists."""
    if not WEB_DIR.exists():
        return

    app.add_middleware(NoCacheMiddleware)

    @app.get("/")
    async def serve_frontend():
        return FileResponse(WEB_DIR / "chat.html")

    @app.get("/dashboard")
    async def serve_dashboard():
        return FileResponse(WEB_DIR / "index.html")

    app.mount("/web", StaticFiles(directory=str(WEB_DIR)), name="web")
