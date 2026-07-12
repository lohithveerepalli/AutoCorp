"""Real navigation deep-link logic — simulates Streamlit sticky widgets."""

from autocorp.ui.navigation import (
    apply_nav_destination,
    build_nav_options,
    normalize_nav_choice,
    option_for_page,
    read_company_selection,
    read_nav_selection,
    set_active_company,
    simulate_sidebar_company_pass,
    sync_company_select_from_active_slug,
    sync_radio_from_nav_page,
)


def test_build_nav_options_badge() -> None:
    opts = build_nav_options(0)
    assert opts[0] == "Dashboard"
    assert opts[3] == "Talk to Agents"
    assert "Approvals" in opts
    assert build_nav_options(3)[4] == "Approvals (3)"


def test_normalize_nav_choice() -> None:
    assert normalize_nav_choice("Approvals (2)") == "Approvals"
    assert normalize_nav_choice("Talk to Agents") == "Talk to Agents"
    assert normalize_nav_choice(None) == "Dashboard"


def test_apply_nav_destination_syncs_radio_key() -> None:
    """Sticky radio simulation: only setting nav_page is NOT enough."""
    session: dict = {"nav_page": "Dashboard", "nav_radio": "Dashboard"}

    # Broken path (what dashboard buttons used to do)
    session["nav_page"] = "Talk to Agents"
    # Without syncing nav_radio, sidebar would re-read Dashboard
    assert session["nav_radio"] == "Dashboard"

    # Fixed path
    apply_nav_destination(session, "Talk to Agents", agent="brain", pending_approvals=0)
    assert session["nav_page"] == "Talk to Agents"
    assert session["nav_radio"] == "Talk to Agents"
    assert session["chat_agent"] == "brain"
    assert session["_nav_programmatic"] is True


def test_sync_radio_from_nav_page_forces_programmatic() -> None:
    session = {
        "nav_page": "Talk to Agents",
        "nav_radio": "Dashboard",  # sticky stale value
        "_nav_programmatic": True,
    }
    selected = sync_radio_from_nav_page(session, pending_approvals=0)
    assert selected == "Talk to Agents"
    assert session["nav_radio"] == "Talk to Agents"
    assert session["_nav_programmatic"] is False

    # User clicks Approvals next
    session["nav_radio"] = "Approvals (1)"
    page = read_nav_selection(session["nav_radio"], session)
    assert page == "Approvals"
    assert session["nav_page"] == "Approvals"


def test_agent_card_deep_link_end_to_end() -> None:
    """Dashboard 'Chat with Brain' → Talk to Agents with agent selected."""
    session: dict = {"nav_page": "Dashboard", "nav_radio": "Dashboard"}
    apply_nav_destination(session, "Talk to Agents", agent="operator", pending_approvals=2)
    # Sidebar mount
    option = sync_radio_from_nav_page(session, pending_approvals=2)
    assert option == "Talk to Agents"
    page = read_nav_selection(option, session)
    assert page == "Talk to Agents"
    assert session["chat_agent"] == "operator"


def test_option_for_page_approvals_badge() -> None:
    assert option_for_page("Approvals", 5) == "Approvals (5)"
    assert option_for_page("Approvals", 0) == "Approvals"


def test_company_select_sticky_overwrite_bug_is_fixed() -> None:
    """Set active+chat / Open company must not be clobbered by sticky selectbox."""
    slugs = ["alpha-co", "beta-co"]
    session: dict = {
        "nav_page": "Companies",
        "nav_radio": "Companies",
        "active_slug": "alpha-co",
        "company_select": "alpha-co",
    }

    # Broken path: only active_slug (historical bug)
    session["active_slug"] = "beta-co"
    session["company_detail"] = "beta-co"
    # Sticky company_select still alpha; sidebar would write active_slug back
    assert session["company_select"] == "alpha-co"
    broken = session["company_select"]  # simulate widget return without sync
    session["active_slug"] = broken
    assert session["active_slug"] == "alpha-co"  # documents the bug class

    # Fixed path
    session = {
        "nav_page": "Companies",
        "nav_radio": "Companies",
        "active_slug": "alpha-co",
        "company_select": "alpha-co",
    }
    apply_nav_destination(
        session,
        "Talk to Agents",
        company_slug="beta-co",
        pending_approvals=0,
    )
    assert session["active_slug"] == "beta-co"
    assert session["company_select"] == "beta-co"
    assert session["_company_programmatic"] is True

    final = simulate_sidebar_company_pass(session, slugs)
    assert final == "beta-co"
    assert session["active_slug"] == "beta-co"
    assert session["company_select"] == "beta-co"
    assert session["nav_page"] == "Talk to Agents"


def test_set_active_company_and_sync() -> None:
    session: dict = {"company_select": "old-co", "active_slug": "old-co"}
    set_active_company(session, "new-co")
    assert session["company_select"] == "new-co"
    sync_company_select_from_active_slug(session, ["old-co", "new-co", "third"])
    assert session["company_select"] == "new-co"
    read_company_selection(session["company_select"], session)
    assert session["active_slug"] == "new-co"
