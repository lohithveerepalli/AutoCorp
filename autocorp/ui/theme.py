"""Theme preference: dark default + light toggle with disk persistence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from autocorp.core.config import get_settings

ThemeName = Literal["dark", "light"]
DEFAULT_THEME: ThemeName = "dark"


def theme_preference_path() -> Path:
    settings = get_settings()
    return settings.data_dir / "ui_theme.json"


def get_theme_preference(path: Path | None = None) -> ThemeName:
    """Read persisted theme. Defaults to dark when missing/invalid."""
    p = path or theme_preference_path()
    if not p.exists():
        return DEFAULT_THEME
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        theme = str(data.get("theme", DEFAULT_THEME)).lower()
        if theme in ("dark", "light"):
            return theme  # type: ignore[return-value]
    except Exception:
        pass
    return DEFAULT_THEME


def set_theme_preference(theme: ThemeName, path: Path | None = None) -> ThemeName:
    """Persist theme preference to disk and return the stored value."""
    if theme not in ("dark", "light"):
        raise ValueError(f"Invalid theme: {theme}")
    p = path or theme_preference_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"theme": theme}, indent=2), encoding="utf-8")
    return theme


def toggle_theme_preference(path: Path | None = None) -> ThemeName:
    current = get_theme_preference(path)
    nxt: ThemeName = "light" if current == "dark" else "dark"
    return set_theme_preference(nxt, path)


def theme_css_variables(theme: ThemeName) -> dict[str, str]:
    """CSS custom properties for Streamlit injection."""
    if theme == "light":
        return {
            "--ac-bg": "#F8FAFC",
            "--ac-bg-elevated": "#FFFFFF",
            "--ac-bg-card": "#FFFFFF",
            "--ac-border": "rgba(15, 23, 42, 0.08)",
            "--ac-text": "#0F172A",
            "--ac-text-muted": "#64748B",
            "--ac-accent": "#059669",
            "--ac-shadow": "0 8px 30px rgba(15, 23, 42, 0.08)",
        }
    return {
        "--ac-bg": "#070B12",
        "--ac-bg-elevated": "#0C1220",
        "--ac-bg-card": "#0F172A",
        "--ac-border": "rgba(148, 163, 184, 0.12)",
        "--ac-text": "#F1F5F9",
        "--ac-text-muted": "#94A3B8",
        "--ac-accent": "#10B981",
        "--ac-shadow": "0 8px 30px rgba(0, 0, 0, 0.35)",
    }
