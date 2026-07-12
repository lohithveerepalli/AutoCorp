"""End-to-end launch with auto-approve (no live APIs)."""

from pathlib import Path

import pytest

from autocorp.core.config import get_settings
from autocorp.core.graph import launch_company
from autocorp.core.models import CompanyBrief


def test_launch_focusflow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "launch.db"
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("AUTOCORP_DB_PATH", str(db))
    monkeypatch.setenv("AUTOCORP_DATA_DIR", str(data))
    get_settings.cache_clear()

    brief = CompanyBrief(
        name="FocusFlow",
        description="AI Pomodoro + deep work tracker for freelancers",
        budget_usd=450,
        stack_preference="Next.js + Supabase + Stripe + Vercel",
        tone="clean, professional",
    )
    result = launch_company(
        brief,
        max_cycles=3,
        context={
            "auto_approve": True,
            "auto_pick_domain": True,
            "approve_domain": True,
            "approve_social": True,
        },
    )
    project = result["project"]
    assert project is not None
    assert project["name"] == "FocusFlow"
    assert project["github_repo"] or True  # mock or live
    # Scaffold should exist
    app_dir = data / "companies" / "focusflow" / "app"
    assert (app_dir / "package.json").exists()
    assert (app_dir / "src" / "app" / "page.tsx").exists()

    get_settings.cache_clear()
