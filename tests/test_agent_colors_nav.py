"""Agent colors + navigation structure from shipped design module."""

from autocorp.ui.design import AGENT_COLORS, NAV_PAGES, agent_color, nav_pages


def test_agent_colors_acceptance() -> None:
    # Brain blue, Operator green, Marketer magenta/purple, Accountant yellow/amber
    assert AGENT_COLORS["brain"].upper() in {"#3B82F6", "#2563EB", "#60A5FA"}
    assert AGENT_COLORS["brain"].lower().startswith("#") and "3b82f6" in AGENT_COLORS["brain"].lower()
    assert AGENT_COLORS["operator"].lower() in {"#22c55e", "#10b981", "#16a34a"}
    marketer = AGENT_COLORS["marketer"].lower()
    assert marketer in {"#a855f7", "#d946ef", "#c026d3", "#9333ea"}
    accountant = AGENT_COLORS["accountant"].lower()
    assert accountant in {"#f59e0b", "#eab308", "#fbbf24"}
    assert agent_color("brain") == AGENT_COLORS["brain"]


def test_nav_pages_order() -> None:
    pages = nav_pages()
    assert pages == NAV_PAGES
    assert pages == [
        "Dashboard",
        "Launch Company",
        "Companies",
        "Talk to Agents",
        "Approvals",
        "Usage & Costs",
        "Settings / Models",
        "Help",
    ]
    assert pages.index("Talk to Agents") == 3
    assert "Approvals" in pages
