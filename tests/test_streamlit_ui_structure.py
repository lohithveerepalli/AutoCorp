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
    assert callable(app_mod.go_to_page)
    assert callable(app_mod.skeleton)


def test_deep_link_buttons_use_go_to_page_not_bare_nav_page() -> None:
    """Regression: setting only nav_page breaks sticky nav_radio."""
    text = (ROOT / "autocorp" / "ui" / "streamlit_app.py").read_text(encoding="utf-8")
    # Dashboard chat buttons
    assert 'go_to_page("Talk to Agents", agent=role)' in text
    # Must not leave the broken pattern near dash chat
    assert "dash_chat_" in text
    # Broken pattern should not appear as assignment before rerun for chat
    assert 'st.session_state.nav_page = "Talk to Agents"' not in text
