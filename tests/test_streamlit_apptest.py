"""AppTest gate — enforces real Streamlit session_state widget rules."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from autocorp.core.config import get_settings
from autocorp.core.models import Project
from autocorp.db.brain import SharedBrain

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "autocorp" / "ui" / "streamlit_app.py"


@pytest.fixture
def seeded_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data = tmp_path / "data"
    data.mkdir()
    db = data / "apptest.db"
    monkeypatch.setenv("AUTOCORP_DB_PATH", str(db))
    monkeypatch.setenv("AUTOCORP_DATA_DIR", str(data))
    get_settings.cache_clear()
    brain = SharedBrain(db)
    a = brain.create_project(Project(name="Alpha Co", description="first", budget_usd=100))
    b = brain.create_project(Project(name="Beta Co", description="second", budget_usd=200))
    yield {"brain": brain, "alpha": a, "beta": b, "data": data}
    get_settings.cache_clear()


def test_apptest_renders_without_session_state_exception(seeded_env) -> None:
    streamlit = pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(APP), default_timeout=30)
    at.run()

    # Must not raise StreamlitAPIException on company_select after-write
    assert not at.exception, f"AppTest exceptions: {at.exception}"

    # Real content assertions (not theater)
    page_text = " ".join(
        [
            *(getattr(t, "value", str(t)) for t in at.title),
            *(getattr(m, "value", str(m)) for m in at.markdown),
            *(getattr(c, "value", str(c)) for c in at.caption),
        ]
    )
    # Dashboard header or KPI labels should appear
    assert (
        "Dashboard" in page_text
        or "Active companies" in page_text
        or "Command center" in page_text
        or any("Dashboard" in str(x) for x in at)
    )

    radios = list(at.sidebar.radio) if at.sidebar.radio else list(at.radio)
    assert len(radios) >= 1
    # Nav options include Talk to Agents
    opts = radios[0].options if hasattr(radios[0], "options") else []
    if opts:
        assert any("Talk to Agents" in str(o) for o in opts)


def test_apptest_programmatic_company_context_survives_sidebar(seeded_env) -> None:
    """Deep-link to Talk to Agents with non-default company must keep that slug."""
    from autocorp.ui.navigation import (
        apply_nav_destination,
        simulate_sidebar_company_pass,
        sync_radio_from_nav_page,
        read_nav_selection,
    )

    alpha = seeded_env["alpha"].slug
    beta = seeded_env["beta"].slug
    session = {
        "nav_page": "Dashboard",
        "nav_radio": "Dashboard",
        "active_slug": alpha,
        "company_select": alpha,
    }
    apply_nav_destination(
        session,
        "Talk to Agents",
        agent="brain",
        company_slug=beta,
        pending_approvals=0,
    )
    # Sidebar radio pass
    opt = sync_radio_from_nav_page(session, 0)
    page = read_nav_selection(opt, session)
    assert page == "Talk to Agents"
    # Sidebar company pass (must not clobber beta; must not rewrite widget post-mount)
    widget_before = session["company_select"]
    final = simulate_sidebar_company_pass(session, [alpha, beta])
    assert final == beta
    assert session["active_slug"] == beta
    assert session["company_select"] == widget_before == beta
    assert session["chat_agent"] == "brain"
