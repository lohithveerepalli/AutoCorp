"""Domain research tests (mock registrars)."""

from pathlib import Path

import pytest

from autocorp.db.brain import SharedBrain
from autocorp.tools.domains import DomainToolkit


@pytest.fixture
def toolkit(tmp_path: Path) -> DomainToolkit:
    return DomainToolkit(SharedBrain(tmp_path / "d.db"))


def test_suggest_and_research(toolkit: DomainToolkit, tmp_path: Path) -> None:
    brain = toolkit.brain
    from autocorp.core.models import Project

    p = brain.create_project(Project(name="FocusFlow", budget_usd=450))
    options = toolkit.research(
        p.id,
        "FocusFlow",
        "AI Pomodoro tracker",
        tlds=["com", "io"],
    )
    assert len(options) > 0
    best = toolkit.best_options(options, budget=50)
    # May be empty if all "taken" — but research should store rows
    stored = brain.list_domain_options(p.id)
    assert len(stored) > 0
    table = toolkit.compare_table(options)
    assert isinstance(table, list)
