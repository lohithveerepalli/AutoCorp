"""Pure navigation helpers for Streamlit sidebar + deep links.

## Streamlit widget-key lifecycle (HARD RULE)

- **Logical keys** may be written anytime:
  `nav_page`, `active_slug`, `chat_agent`, `company_detail`
- **Widget keys** may be written **only in pre-widget sync helpers**:
  `nav_radio`, `company_select`
- **Never** write a widget key inside any `read_*_selection` after the
  corresponding widget has been instantiated.

Programmatic navigation flow:
1. `apply_nav_destination` / `set_active_company` set logical keys + widget keys
   and flags (`_nav_programmatic`, `_company_programmatic`)
2. Before widgets: `sync_*_from_*` force widget keys if flags set
3. After widgets: `read_*_selection` updates **logical keys only**
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
    """Programmatic navigation: logical keys + pre-mount widget keys + flags."""
    canonical = normalize_nav_choice(page)
    if canonical not in NAV_PAGES:
        raise ValueError(f"Unknown page: {page}")
    session["nav_page"] = canonical
    # Widget key write is intentional here (pre-mount / before next run's widgets)
    session["nav_radio"] = option_for_page(canonical, pending_approvals)
    session["_nav_programmatic"] = True
    if agent is not None:
        session["chat_agent"] = agent
    if company_slug is not None:
        set_active_company(session, company_slug)
    return canonical


def set_active_company(session: MutableMapping[str, Any], company_slug: str) -> str:
    """Programmatically select a company (logical + widget key, pre-mount only)."""
    slug = str(company_slug)
    session["active_slug"] = slug
    session["company_detail"] = slug
    # Widget key — only safe before selectbox is created (pre-rerun / sync helper)
    session["company_select"] = slug
    session["_company_programmatic"] = True
    return slug


def sync_radio_from_nav_page(
    session: MutableMapping[str, Any],
    pending_approvals: int = 0,
) -> str:
    """Before st.radio(key='nav_radio'), align sticky widget key with nav_page."""
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
    """Before st.selectbox(key='company_select'), align sticky widget key."""
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

    return session.get("company_select") if session.get("company_select") in slugs else desired


def read_company_selection(
    choice: str | None,
    session: MutableMapping[str, Any] | None = None,
) -> str | None:
    """After selectbox returns: update LOGICAL keys only (never company_select)."""
    if choice is None:
        if session is not None:
            session["active_slug"] = None
        return None
    if session is not None:
        session["active_slug"] = choice
        # Do NOT write session["company_select"] — widget already owns that key
        session["company_detail"] = choice
    return choice


def read_nav_selection(
    choice: str | None,
    session: MutableMapping[str, Any] | None = None,
) -> str:
    """After radio returns: update LOGICAL nav_page only (never nav_radio)."""
    page = normalize_nav_choice(choice)
    if session is not None:
        session["nav_page"] = page
        # Do NOT write session["nav_radio"] after radio is mounted
    return page


def simulate_sidebar_company_pass(
    session: MutableMapping[str, Any],
    slugs: Sequence[str],
) -> str | None:
    """Test helper: pre-sync widget key, then post-read logical key only."""
    sync_company_select_from_active_slug(session, slugs)
    choice = session.get("company_select")
    if choice not in slugs:
        choice = slugs[0] if slugs else None
    # Simulate widget sticky value without rewriting company_select after "mount"
    return read_company_selection(choice, session)
