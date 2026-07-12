"""Pure navigation helpers for Streamlit sidebar + deep links.

Streamlit keyed widgets ignore `index` after first mount; programmatic
navigation must write widget keys (`nav_radio`, `company_select`) as well as
logical keys (`nav_page`, `active_slug`).
"""

from __future__ import annotations

from typing import Any, MutableMapping, Sequence

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
    """Programmatic navigation: sync page + radio + optional company + agent.

    Sets `_nav_programmatic` and, when company_slug is provided,
    `_company_programmatic` so the sidebar can force-sync sticky widget keys
    before widgets are created.
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
        set_active_company(session, company_slug)
    return canonical


def set_active_company(session: MutableMapping[str, Any], company_slug: str) -> str:
    """Programmatically select a company (syncs active_slug + company_select)."""
    slug = str(company_slug)
    session["active_slug"] = slug
    session["company_detail"] = slug
    session["company_select"] = slug
    session["_company_programmatic"] = True
    return slug


def sync_radio_from_nav_page(
    session: MutableMapping[str, Any],
    pending_approvals: int = 0,
) -> str:
    """Before rendering st.radio(key='nav_radio'), align sticky key with nav_page."""
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
        current = session.get("nav_radio")
        if current not in options:
            session["nav_radio"] = desired

    session["nav_page"] = page
    return session["nav_radio"]


def sync_company_select_from_active_slug(
    session: MutableMapping[str, Any],
    slugs: Sequence[str],
) -> str | None:
    """Before st.selectbox(key='company_select'), align sticky key with active_slug.

    Returns the slug that should be selected, or None if no companies.
    """
    if not slugs:
        session["active_slug"] = None
        session.pop("company_select", None)
        session["_company_programmatic"] = False
        return None

    desired = session.get("active_slug")
    if desired not in slugs:
        desired = slugs[0]
        session["active_slug"] = desired

    if session.get("_company_programmatic"):
        session["company_select"] = desired
        session["_company_programmatic"] = False
    elif session.get("company_select") not in slugs:
        session["company_select"] = desired
    elif "company_select" not in session:
        session["company_select"] = desired

    # After programmatic force, company_select matches active_slug.
    # After user click, company_select is source of truth (read after widget).
    return session.get("company_select") if session.get("company_select") in slugs else desired


def read_company_selection(
    choice: str | None,
    session: MutableMapping[str, Any] | None = None,
) -> str | None:
    """After selectbox returns, write active_slug from the sticky widget value."""
    if choice is None:
        if session is not None:
            session["active_slug"] = None
        return None
    if session is not None:
        session["active_slug"] = choice
        session["company_select"] = choice
    return choice


def read_nav_selection(
    choice: str | None,
    session: MutableMapping[str, Any] | None = None,
) -> str:
    """After radio returns, normalize and optionally write session.nav_page."""
    page = normalize_nav_choice(choice)
    if session is not None:
        session["nav_page"] = page
    return page


def simulate_sidebar_company_pass(
    session: MutableMapping[str, Any],
    slugs: Sequence[str],
) -> str | None:
    """Test helper: full sticky selectbox cycle (sync → widget → write active_slug)."""
    sync_company_select_from_active_slug(session, slugs)
    # Widget returns sticky company_select
    choice = session.get("company_select")
    if choice not in slugs:
        choice = slugs[0] if slugs else None
    return read_company_selection(choice, session)
