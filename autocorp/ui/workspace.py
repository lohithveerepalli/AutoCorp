"""Pure builders for project workspace header and System / Next Actions panel."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from autocorp.core.models import AgentRole, ApprovalRequest, Project
from autocorp.db.brain import SharedBrain
from autocorp.ui.design import AGENT_LABELS, AGENT_ROLES, agent_color


def budget_remaining(project: Project) -> float:
    return float(project.budget_usd or 0) - float(project.spent_usd or 0)


def last_activity_iso(brain: SharedBrain, project_id: str) -> str:
    """Best-effort last activity timestamp from message bus or project.updated_at."""
    thread = brain.get_thread(project_id, limit=1)
    if thread:
        # get_thread returns chronological latest-N; last item is newest among them
        # With limit=1 and latest-N, the single item is the newest overall
        ts = thread[-1].created_at
        if hasattr(ts, "isoformat"):
            return ts.isoformat()
        return str(ts)
    if project := brain.get_project(project_id):
        if project.updated_at:
            return project.updated_at.isoformat() if hasattr(project.updated_at, "isoformat") else str(project.updated_at)
    return ""


def project_header_data(brain: SharedBrain, project: Project) -> dict[str, Any]:
    """Shipped header fields for the project workspace."""
    return {
        "name": project.name,
        "slug": project.slug,
        "status": project.status,
        "budget_usd": float(project.budget_usd or 0),
        "spent_usd": float(project.spent_usd or 0),
        "budget_remaining": budget_remaining(project),
        "domain": project.domain or "",
        "last_activity": last_activity_iso(brain, project.id),
        "github_repo": project.github_repo or "",
        "vercel_url": project.vercel_url or "",
    }


def agent_activity_rows(brain: SharedBrain, project_id: str) -> list[dict[str, Any]]:
    """What agents are currently doing (from SharedBrain agent_status)."""
    rows: list[dict[str, Any]] = []
    for s in brain.get_agent_statuses(project_id):
        role = s.agent.value if hasattr(s.agent, "value") else str(s.agent)
        status = s.status.value if hasattr(s.status, "value") else str(s.status)
        rows.append(
            {
                "agent": role,
                "label": AGENT_LABELS.get(role, role.title()),
                "color": agent_color(role),
                "status": status,
                "task": s.current_task or "Idle",
                "loop_count": s.loop_count or 0,
                "last_heartbeat": s.last_heartbeat.isoformat()
                if getattr(s, "last_heartbeat", None) and hasattr(s.last_heartbeat, "isoformat")
                else str(getattr(s, "last_heartbeat", "") or ""),
            }
        )
    # Ensure all four roles present
    have = {r["agent"] for r in rows}
    for role in AGENT_ROLES:
        if role not in have:
            rows.append(
                {
                    "agent": role,
                    "label": AGENT_LABELS[role],
                    "color": agent_color(role),
                    "status": "idle",
                    "task": "No status yet",
                    "loop_count": 0,
                    "last_heartbeat": "",
                }
            )
    order = {r: i for i, r in enumerate(AGENT_ROLES)}
    rows.sort(key=lambda r: order.get(r["agent"], 99))
    return rows


def pending_approvals_for_project(
    brain: SharedBrain, project_id: str
) -> list[dict[str, Any]]:
    """Pending approvals filtered to this project, as serializable dicts."""
    out: list[dict[str, Any]] = []
    for a in brain.list_pending_approvals(project_id):
        out.append(
            {
                "id": a.id,
                "action": a.action,
                "description": a.description or "",
                "amount_usd": float(a.amount_usd or 0),
                "irreversible": bool(a.irreversible),
                "requested_by": a.requested_by.value
                if hasattr(a.requested_by, "value")
                else str(a.requested_by),
                "options": a.options or [],
            }
        )
    return out


def recommended_next_steps(
    project: Project,
    activities: list[dict[str, Any]],
    pending: list[dict[str, Any]],
) -> list[str]:
    """CEO-oriented next steps derived from project + agent + approval state."""
    steps: list[str] = []
    if pending:
        steps.append(
            f"Review {len(pending)} pending approval(s) — money or irreversible actions waiting."
        )
    if not project.domain:
        steps.append("Work with Operator to pick and approve a domain within budget.")
    if not project.vercel_url and not project.github_repo:
        steps.append("Ask Brain to scaffold, push GitHub, and deploy when domain is ready.")
    elif not project.vercel_url:
        steps.append("Ask Brain to finish production deploy (Vercel URL still empty).")
    busy = [a for a in activities if str(a.get("status", "")).lower() in ("running", "waiting_approval")]
    if busy:
        steps.append(
            "Agents in motion: "
            + ", ".join(f"{a['label']} ({a['status']})" for a in busy)
            + "."
        )
    if budget_remaining(project) < 50:
        steps.append("Budget is tight — ask Accountant for a P&L review before new spend.")
    if not steps:
        steps.append("Chat with any agent in the 2×2 grid, or run another autonomous cycle from CLI.")
        steps.append("Use Marketer for growth posts once the production URL is live.")
    return steps[:6]


def system_next_actions_panel(
    brain: SharedBrain, project: Project
) -> dict[str, Any]:
    """Full System / Next Actions payload for the workspace right/bottom panel."""
    activities = agent_activity_rows(brain, project.id)
    pending = pending_approvals_for_project(brain, project.id)
    return {
        "project_id": project.id,
        "project_name": project.name,
        "agent_activity": activities,
        "needs_human_approval": [
            {
                "summary": f"{p['action']}: {p['description'][:120]}",
                "amount_usd": p["amount_usd"],
                "irreversible": p["irreversible"],
                "id": p["id"],
            }
            for p in pending
        ],
        "recommended_next_steps": recommended_next_steps(project, activities, pending),
        "pending_approvals": pending,
    }


# Per-agent quick action chips (relevant to role)
AGENT_QUICK_ACTIONS: dict[str, list[dict[str, str]]] = {
    "brain": [
        {"id": "review_code", "label": "Review last code", "prompt": "Review the latest code and architecture for this company. List risks and next engineering tasks."},
        {"id": "deploy_status", "label": "Deploy status", "prompt": "Summarize GitHub, Supabase, and Vercel status and what is left to ship to production."},
        {"id": "next_eng", "label": "Next eng steps", "prompt": "Propose the next three engineering steps for this product in the next 48 hours."},
    ],
    "operator": [
        {"id": "domain_opts", "label": "Domain options", "prompt": "List current domain options, prices, and your purchase recommendation within budget."},
        {"id": "email_status", "label": "Email / infra", "prompt": "Report on email accounts, DNS, and infrastructure health for this company."},
        {"id": "ops_next", "label": "Ops next steps", "prompt": "What ops actions should we take next? Any blockers needing CEO approval?"},
    ],
    "marketer": [
        {"id": "brand", "label": "Brand summary", "prompt": "Summarize brand kit, handles, and positioning for this company."},
        {"id": "content", "label": "Launch content", "prompt": "Show launch content status across X, LinkedIn, Instagram, and TikTok."},
        {"id": "growth", "label": "Growth plan", "prompt": "Propose the next growth experiments for the next two weeks."},
    ],
    "accountant": [
        {"id": "show_budget", "label": "Show budget", "prompt": "Show budget, spent by category, pending costs, and remaining runway."},
        {"id": "pnl", "label": "Live P&L", "prompt": "Give a concise P&L report and any budget alerts."},
        {"id": "spend_review", "label": "Spend review", "prompt": "Which pending or proposed spends should the CEO approve or reject?"},
    ],
}


def quick_actions_for_agent(agent: str) -> list[dict[str, str]]:
    return list(AGENT_QUICK_ACTIONS.get(agent.lower(), []))
