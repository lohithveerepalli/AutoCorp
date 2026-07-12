"""FastAPI application factory for AutoCorp Web UI."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from autocorp import __version__
from autocorp.web.api import router as api_router

WEB_DIR = Path(__file__).resolve().parent
STATIC_DIR = WEB_DIR / "static"
TEMPLATES_DIR = WEB_DIR / "templates"
INDEX_HTML = TEMPLATES_DIR / "index.html"


def create_app() -> FastAPI:
    app = FastAPI(
        title="AutoCorp",
        description="Autonomous multi-agent AI Company Operating System",
        version=__version__,
    )

    app.include_router(api_router, prefix="/api")

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        if not INDEX_HTML.is_file():
            raise HTTPException(
                status_code=500,
                detail=(
                    f"UI template missing at {INDEX_HTML}. "
                    "Restore autocorp/web/templates/index.html"
                ),
            )
        return HTMLResponse(
            content=INDEX_HTML.read_text(encoding="utf-8"),
            media_type="text/html; charset=utf-8",
        )

    @app.get("/health")
    async def health() -> dict:
        return {
            "ok": True,
            "service": "autocorp",
            "version": __version__,
            "templates": str(TEMPLATES_DIR),
            "index_exists": INDEX_HTML.is_file(),
        }

    return app


app = create_app()
