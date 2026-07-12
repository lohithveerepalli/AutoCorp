"""Tests for SharedBrain SQLite store."""

from pathlib import Path

import pytest

from autocorp.core.models import (
    AgentRole,
    CostCategory,
    CostEntry,
    Message,
    Project,
)
from autocorp.db.brain import SharedBrain


@pytest.fixture
def brain(tmp_path: Path) -> SharedBrain:
    return SharedBrain(tmp_path / "test.db")


def test_create_and_get_project(brain: SharedBrain) -> None:
    p = brain.create_project(
        Project(name="FocusFlow", description="Pomodoro app", budget_usd=450)
    )
    assert p.slug == "focusflow"
    loaded = brain.get_project(p.id)
    assert loaded is not None
    assert loaded.name == "FocusFlow"
    assert loaded.budget_usd == 450


def test_messaging(brain: SharedBrain) -> None:
    p = brain.create_project(Project(name="Acme", budget_usd=100))
    brain.send_message(
        Message(
            project_id=p.id,
            from_agent=AgentRole.OPERATOR,
            to_agent=AgentRole.ACCOUNTANT,
            subject="Domain options",
            body="Please review",
        )
    )
    inbox = brain.get_inbox(p.id, AgentRole.ACCOUNTANT, unread_only=True)
    assert len(inbox) == 1
    assert inbox[0].subject == "Domain options"


def test_budget_tracking(brain: SharedBrain) -> None:
    p = brain.create_project(Project(name="BudgetCo", budget_usd=100))
    brain.add_cost(
        CostEntry(
            project_id=p.id,
            category=CostCategory.DOMAIN,
            amount_usd=12.5,
            description="example.com",
            approved=True,
            approved_by="test",
        )
    )
    snap = brain.budget_snapshot(p.id)
    assert snap.spent_usd == 12.5
    assert snap.remaining_usd == 87.5


def test_get_thread_returns_latest_n_not_oldest(brain: SharedBrain) -> None:
    """Recent activity / company messages must show newest messages, not first N."""
    from autocorp.core.models import Message, AgentRole
    import time

    p = brain.create_project(Project(name="ThreadCo", budget_usd=50))
    for i in range(20):
        brain.send_message(
            Message(
                project_id=p.id,
                from_agent=AgentRole.BRAIN,
                to_agent=AgentRole.OPERATOR,
                subject=f"msg-{i}",
                body=f"body-{i}",
            )
        )
        # tiny spacing so created_at ordering is stable if timestamps collide
        time.sleep(0.001)
    thread = brain.get_thread(p.id, limit=12)
    assert len(thread) == 12
    subjects = [m.subject for m in thread]
    # Must be chronological among the *latest* 12
    assert subjects[0] == "msg-8"
    assert subjects[-1] == "msg-19"
    assert "msg-0" not in subjects
    assert "msg-7" not in subjects
