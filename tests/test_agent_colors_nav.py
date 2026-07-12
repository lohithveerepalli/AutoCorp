"""Agent colors for the four chat panes."""

from autocorp.ui.design import AGENT_COLORS, agent_color
from autocorp.ui.workspace import quick_actions_for_agent


def test_agent_colors_acceptance() -> None:
    assert "3b82f6" in AGENT_COLORS["brain"].lower()
    assert AGENT_COLORS["operator"].lower() in {"#22c55e", "#10b981", "#16a34a"}
    assert AGENT_COLORS["marketer"].lower() in {"#a855f7", "#d946ef", "#c026d3", "#9333ea"}
    assert AGENT_COLORS["accountant"].lower() in {"#f59e0b", "#eab308", "#fbbf24"}
    assert agent_color("brain") == AGENT_COLORS["brain"]


def test_sidebar_shell_labels_in_app_source() -> None:
    from pathlib import Path

    text = (
        Path(__file__).resolve().parents[1]
        / "autocorp"
        / "ui"
        / "streamlit_app.py"
    ).read_text(encoding="utf-8")
    for label in ("+ New Project", "Approvals", "Usage & Costs", "Settings"):
        assert label in text


def test_role_quick_actions_exist() -> None:
    for role in ("brain", "operator", "marketer", "accountant"):
        assert quick_actions_for_agent(role)
