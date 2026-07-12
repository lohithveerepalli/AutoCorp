"""Project workspace builders + sidebar layout structure (shipped paths)."""

from pathlib import Path

import pytest

from autocorp.core.models import AgentRole, ApprovalRequest, Project
from autocorp.db.brain import SharedBrain
from autocorp.ui.design import AGENT_COLORS, AGENT_ROLES
from autocorp.ui.workspace import (
    agent_activity_rows,
    budget_remaining,
    pending_approvals_for_project,
    project_header_data,
    quick_actions_for_agent,
    recommended_next_steps,
    system_next_actions_panel,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def brain_proj(tmp_path: Path):
    b = SharedBrain(tmp_path / "ws.db")
    p = b.create_project(
        Project(
            name="FocusFlow",
            description="Pomodoro app",
            budget_usd=450,
            spent_usd=9.17,
            status="active",
            domain="appfocusflow.com",
        )
    )
    return b, p


def test_project_header_fields(brain_proj) -> None:
    brain, p = brain_proj
    h = project_header_data(brain, p)
    assert h["name"] == "FocusFlow"
    assert h["status"] == "active"
    assert h["budget_remaining"] == pytest.approx(450 - 9.17)
    assert "last_activity" in h
    assert budget_remaining(p) == h["budget_remaining"]


def test_system_panel_structure(brain_proj) -> None:
    brain, p = brain_proj
    brain.create_approval(
        ApprovalRequest(
            project_id=p.id,
            requested_by=AgentRole.OPERATOR,
            action="purchase_domain",
            description="Buy domain",
            amount_usd=12.0,
            irreversible=True,
        )
    )
    panel = system_next_actions_panel(brain, p)
    assert panel["project_name"] == "FocusFlow"
    assert len(panel["agent_activity"]) >= 4
    roles = {a["agent"] for a in panel["agent_activity"]}
    assert set(AGENT_ROLES).issubset(roles)
    assert len(panel["pending_approvals"]) == 1
    assert panel["needs_human_approval"]
    assert panel["recommended_next_steps"]
    assert any("approval" in s.lower() or "pending" in s.lower() for s in panel["recommended_next_steps"])


def test_agent_colors_for_panes() -> None:
    assert AGENT_COLORS["brain"].lower() == "#3b82f6"
    assert AGENT_COLORS["operator"].lower() == "#22c55e"
    assert AGENT_COLORS["marketer"].lower() in {"#a855f7", "#d946ef"}
    assert AGENT_COLORS["accountant"].lower() in {"#f59e0b", "#eab308"}


def test_quick_actions_per_agent() -> None:
    for role in AGENT_ROLES:
        chips = quick_actions_for_agent(role)
        assert len(chips) >= 2
        assert all("label" in c and "prompt" in c for c in chips)


def test_streamlit_app_workspace_layout_source() -> None:
    text = (ROOT / "autocorp" / "ui" / "streamlit_app.py").read_text(encoding="utf-8")
    # Sidebar contract
    assert "+ New Project" in text
    assert "Approvals" in text
    assert "Usage & Costs" in text
    assert "Settings" in text
    assert "btn_theme" in text or "Theme" in text
    assert "list_projects" in text
    # Workspace
    assert "render_project_workspace" in text
    assert "render_agent_pane" in text
    assert "render_system_panel" in text
    assert "System / Next Actions" in text
    for role in ("brain", "operator", "marketer", "accountant"):
        assert f'render_agent_pane(project, "{role}")' in text
    # Four panes + system
    # Four role call sites in workspace layout (def line may also match)
    for role in ("brain", "operator", "marketer", "accountant"):
        assert f'render_agent_pane(project, "{role}")' in text
    assert "project_header_data" in text
    assert "system_next_actions_panel" in text


def test_pending_approvals_filtered(brain_proj) -> None:
    brain, p = brain_proj
    other = brain.create_project(Project(name="Other", budget_usd=10))
    brain.create_approval(
        ApprovalRequest(
            project_id=p.id,
            requested_by=AgentRole.ACCOUNTANT,
            action="spend",
            description="A",
            amount_usd=1,
        )
    )
    brain.create_approval(
        ApprovalRequest(
            project_id=other.id,
            requested_by=AgentRole.ACCOUNTANT,
            action="spend",
            description="B",
            amount_usd=2,
        )
    )
    mine = pending_approvals_for_project(brain, p.id)
    assert len(mine) == 1
    assert mine[0]["description"] == "A"
