"""Structural checks for multi-agent project OS Streamlit UI."""

from pathlib import Path

import autocorp.ui.streamlit_app as app_mod
from autocorp.ui.design import AGENT_ROLES

ROOT = Path(__file__).resolve().parents[1]


def test_streamlit_entry_exists() -> None:
    path = ROOT / "autocorp" / "ui" / "streamlit_app.py"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "def main()" in text
    assert "render_project_workspace" in text
    assert "render_sidebar" in text


def test_streamlit_in_dependencies() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "streamlit" in pyproject
    assert "streamlit-extras" in pyproject


def test_branding_css_hides_streamlit_chrome() -> None:
    css = (ROOT / "autocorp" / "ui" / "assets" / "streamlit_theme.css").read_text(
        encoding="utf-8"
    )
    assert "#MainMenu" in css
    assert "footer" in css
    assert "stHeader" in css or "stToolbar" in css
    assert "white-space: pre-wrap" in css


def test_sidebar_and_workspace_contract() -> None:
    text = (ROOT / "autocorp" / "ui" / "streamlit_app.py").read_text(encoding="utf-8")
    for needle in (
        "+ New Project",
        "Approvals",
        "Usage & Costs",
        "Settings",
        "render_agent_pane",
        "System / Next Actions",
        "budget_remaining",
        "format_chat_html",
        "send_user_message",
    ):
        assert needle in text or (
            needle == "budget_remaining" and "project_header_data" in text
        )
    for role in AGENT_ROLES:
        assert f'render_agent_pane(project, "{role}")' in text


def test_cli_ui_points_at_streamlit() -> None:
    cli = (ROOT / "autocorp" / "cli" / "main.py").read_text(encoding="utf-8")
    assert "streamlit" in cli
    assert "streamlit_app.py" in cli


def test_streamlit_app_module_importable() -> None:
    assert callable(app_mod.main)
    assert callable(app_mod.render_project_workspace)
    assert callable(app_mod.render_agent_pane)
    assert callable(app_mod.render_system_panel)
    assert callable(app_mod.skeleton)
    assert callable(app_mod.format_chat_html)
