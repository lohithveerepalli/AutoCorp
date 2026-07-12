"""Pure navigation helpers for Streamlit sidebar + deep links.

Streamlit keyed widgets ignore `index` after first mount; programmatic
navigation must write the widget key (`nav_radio`) as well as `nav_page`.
"""

from __future__ import annotations

from typing import Any, MutableMapping

from autocorp.ui.design import NAV_PAGES, nav_pages


def build_nav_options(pending_approvals: int = 0) -> list[str]:
    """Sidebar labels; Approvals gets a badge count when pending > 0."""
    options: list[str] = []
    for lab in nav_pages():
        if lab == "Approvals" and pending_approvals > 0:
            options.append(f"Approvals ({pending_approvals})")
        else:
            options.append(lab)
    return options


def normalize_nav_choice(choice: str | None) -> str:
    """Map radio label (possibly badged) back to canonical page name."""
    if not choice:
        return "Dashboard"
    if choice == "Approvals" or choice.startswith("Approvals ("):
        return "Approvals"
    if choice in NAV_PAGES:
        return choice
    # Fallback: strip badge
    base = choice.split(" (", 1)[0]
    return base if base in NAV_PAGES else "Dashboard"


def option_for_page(page: str, pending_approvals: int = 0) -> str:
    """Canonical page → exact radio option string for current badge state."""
    page = normalize_nav_choice(page)
    if page == "Approvals" and pending_approvals > 0:
        return f"Approvals ({pending_approvals})"
    return page


def apply_nav_destination(
    session: MutableMapping[str, Any],
    page: str,
    *,
    agent: str | None = None,
    pending_approvals: int = 0,
    company_slug: str | None = None,
) -> str:
    """Programmatic navigation: set nav_page + nav_radio + optional chat agent.

    Returns the canonical page name. Sets `_nav_programmatic` so the sidebar
    can force-sync the sticky radio key before the widget is created.
    """
    canonical = normalize_nav_choice(page)
    if canonical not in NAV_PAGES:
        raise ValueError(f"Unknown page: {page}")
    session["nav_page"] = canonical
    session["nav_radio"] = option_for_page(canonical, pending_approvals)
    session["_nav_programmatic"] = True
    if agent is not None:
        session["chat_agent"] = agent
    if company_slug is not None:
        session["active_slug"] = company_slug
        session["company_detail"] = company_slug
    return canonical


def sync_radio_from_nav_page(
    session: MutableMapping[str, Any],
    pending_approvals: int = 0,
) -> str:
    """Before rendering st.radio(key='nav_radio'), align sticky key with nav_page.

    If a programmatic navigation just happened, always overwrite nav_radio.
    Returns the option string that should be selected.
    """
    page = normalize_nav_choice(session.get("nav_page", "Dashboard"))
    desired = option_for_page(page, pending_approvals)
    options = build_nav_options(pending_approvals)
    if desired not in options:
        desired = options[0] if options else "Dashboard"
        page = normalize_nav_choice(desired)

    if session.get("_nav_programmatic"):
        session["nav_radio"] = desired
        session["_nav_programmatic"] = False
    elif "nav_radio" not in session:
        session["nav_radio"] = desired
    else:
        # Keep radio if user clicked it; ensure nav_page follows on read path
        current = session.get("nav_radio")
        if current not in options:
            session["nav_radio"] = desired

    session["nav_page"] = page
    return session["nav_radio"]


def read_nav_selection(
    choice: str | None,
    session: MutableMapping[str, Any] | None = None,
) -> str:
    """After radio returns, normalize and optionally write session.nav_page."""
    page = normalize_nav_choice(choice)
    if session is not None:
        session["nav_page"] = page
    return page
