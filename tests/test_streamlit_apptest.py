"""AppTest smoke for multi-agent project workspace UI."""

from __future__ import annotations

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
    p = brain.create_project(
        Project(name="FocusFlow", description="demo", budget_usd=450, spent_usd=10)
    )
    yield {"brain": brain, "project": p, "data": data}
    get_settings.cache_clear()


def test_apptest_workspace_loads_without_exception(seeded_env) -> None:
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(APP), default_timeout=45)
    at.run()
    assert not at.exception, f"AppTest exceptions: {at.exception}"

    # Sidebar has New Project
    labels = [b.label for b in at.sidebar.button]
    assert any("New Project" in (lab or "") for lab in labels), labels

    page_bits = " ".join(
        [
            *(getattr(m, "value", str(m)) for m in at.markdown),
            *(getattr(c, "value", str(c)) for c in at.caption),
        ]
    )
    # Workspace header or system panel when project auto-selected
    assert (
        "FocusFlow" in page_bits
        or "System / Next Actions" in page_bits
        or "Executive team" in page_bits
        or "Select or create" in page_bits
    )


def test_workspace_helpers_drive_header_for_seeded_project(seeded_env) -> None:
    from autocorp.ui.workspace import project_header_data, system_next_actions_panel

    p = seeded_env["project"]
    brain = seeded_env["brain"]
    h = project_header_data(brain, p)
    assert h["name"] == "FocusFlow"
    assert h["budget_remaining"] == pytest.approx(440.0)
    panel = system_next_actions_panel(brain, p)
    assert len(panel["agent_activity"]) >= 4
    assert isinstance(panel["recommended_next_steps"], list)
