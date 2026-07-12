"""Design tokens for AutoCorp Streamlit CEO dashboard."""

from __future__ import annotations

from typing import Final

# Color-coded agents (acceptance criteria)
AGENT_COLORS: Final[dict[str, str]] = {
    "brain": "#3B82F6",       # Blue
    "operator": "#22C55E",    # Green
    "marketer": "#A855F7",    # Magenta / Purple
    "accountant": "#F59E0B",  # Yellow / Amber
}

AGENT_LABELS: Final[dict[str, str]] = {
    "brain": "Brain",
    "operator": "Operator",
    "marketer": "Marketer",
    "accountant": "Accountant",
}

AGENT_ROLES: Final[list[str]] = ["brain", "operator", "marketer", "accountant"]

AGENT_BLURBS: Final[dict[str, str]] = {
    "brain": "Product ownership · code · GitHub · deploy",
    "operator": "Domains · email · infrastructure",
    "marketer": "Brand · social · growth",
    "accountant": "Budget · Stripe · P&L",
}

# Ordered sidebar navigation (acceptance criteria)
NAV_PAGES: Final[list[str]] = [
    "Dashboard",
    "Launch Company",
    "Companies",
    "Talk to Agents",
    "Approvals",
    "Usage & Costs",
    "Settings / Models",
    "Help",
]

QUICK_ACTION_CHIPS: Final[list[dict[str, str]]] = [
    {"id": "review_code", "label": "Review last code", "prompt": "Review the last code and architecture decisions for this company. Summarize risks and next engineering steps."},
    {"id": "show_budget", "label": "Show budget", "prompt": "Show me the current budget, spend by category, pending approvals, and remaining runway."},
    {"id": "next_steps", "label": "Propose next steps", "prompt": "Propose the next three highest-leverage actions for this company in the next 48 hours."},
]


def nav_pages() -> list[str]:
    """Shipped nav definition for UI + tests."""
    return list(NAV_PAGES)


def agent_color(role: str) -> str:
    return AGENT_COLORS.get(role.lower(), "#94A3B8")
