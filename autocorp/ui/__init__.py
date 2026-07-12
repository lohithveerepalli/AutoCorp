"""UI layer: Rich CLI + Streamlit CEO dashboard."""

from autocorp.ui.console import AgentConsole, banner, get_console
from autocorp.ui.design import AGENT_COLORS, NAV_PAGES, nav_pages
from autocorp.ui.setup_wizard import run_setup_wizard
from autocorp.ui.theme import get_theme_preference, set_theme_preference

__all__ = [
    "AgentConsole",
    "banner",
    "get_console",
    "run_setup_wizard",
    "AGENT_COLORS",
    "NAV_PAGES",
    "nav_pages",
    "get_theme_preference",
    "set_theme_preference",
]
