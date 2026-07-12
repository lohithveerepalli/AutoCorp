"""Structural checks for Streamlit UI entry, branding CSS, screens."""

from pathlib import Path

import autocorp.ui.streamlit_app as app_mod
from autocorp.ui.design import NAV_PAGES, QUICK_ACTION_CHIPS


ROOT = Path(__file__).resolve().parents[1]


def test_streamlit_entry_exists() -> None:
    path = ROOT / "autocorp" / "ui" / "streamlit_app.py"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "def main()" in text
    assert "Talk to Agents" in text
    assert "streamlit" in text


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


def test_nav_and_screens_in_source() -> None:
    text = (ROOT / "autocorp" / "ui" / "streamlit_app.py").read_text(encoding="utf-8")
    for page in NAV_PAGES:
        assert page in text
    for section in (
        "page_dashboard",
        "page_launch",
        "page_companies",
        "page_talk_to_agents",
        "page_approvals",
        "page_usage",
        "page_settings",
        "page_help",
    ):
        assert f"def {section}" in text
    # Company detail tabs
    for tab in ("Overview", "Agents", "Messages", "P&L", "Infrastructure", "Approvals"):
        assert tab in text
    # Chat UX
    assert "Clear chat" in text
    assert "Export chat" in text
    assert "QUICK_ACTION_CHIPS" in text
    # Chip labels live in shipped design module and are rendered via that list
    labels = {c["label"] for c in QUICK_ACTION_CHIPS}
    assert "Review last code" in labels
    assert "Show budget" in labels
    assert "Propose next steps" in labels
    assert "empty_state" in text
    assert "skeleton" in text or "ac-skeleton" in text
    assert "toast" in text


def test_cli_ui_points_at_streamlit() -> None:
    cli = (ROOT / "autocorp" / "cli" / "main.py").read_text(encoding="utf-8")
    assert "streamlit" in cli
    assert "streamlit_app.py" in cli


def test_streamlit_app_module_importable() -> None:
    assert callable(app_mod.main)
    assert callable(app_mod.page_talk_to_agents)
