"""FastAPI application factory for AutoCorp Web UI."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from autocorp import __version__
from autocorp.web.api import router as api_router

WEB_DIR = Path(__file__).resolve().parent
STATIC_DIR = WEB_DIR / "static"
TEMPLATES_DIR = WEB_DIR / "templates"


def create_app() -> FastAPI:
    app = FastAPI(
        title="AutoCorp",
        description="Autonomous multi-agent AI Company Operating System",
        version=__version__,
    )

    app.include_router(api_router, prefix="/api")
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(TEMPLATES_DIR / "index.html")

    @app.get("/health")
    async def health() -> dict:
        return {"ok": True, "service": "autocorp", "version": __version__}

    return app


app = create_app()
