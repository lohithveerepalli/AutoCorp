"""REST API for AutoCorp Web UI."""

from __future__ import annotations

import threading
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from autocorp import __version__
from autocorp.core.config import (
    MODEL_CATALOG,
    USAGE_PROFILES,
    AgentModelConfig,
    UserConfig,
    estimate_monthly_cost,
    get_available_models_for_role,
    get_settings,
    load_user_config,
    save_user_config,
)
from autocorp.core.graph import continue_company, launch_company
from autocorp.core.llm import model_ready
from autocorp.core.models import CompanyBrief
from autocorp.db.brain import SharedBrain
from autocorp.tools.budget import BudgetToolkit

router = APIRouter()

# In-process launch job tracking (simple; one active job)
_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()


def _brain() -> SharedBrain:
    return SharedBrain(get_settings().db_path)


# ── Models ───────────────────────────────────────────────────


class SaveConfigBody(BaseModel):
    models: AgentModelConfig
    budget_alert_usd: float = 50.0
    default_company_budget_usd: float = 500.0
    require_human_approval: bool = True
    usage_profile: Literal["light", "medium", "heavy"] = "medium"


class CostEstimateBody(BaseModel):
    models: AgentModelConfig
    profile: Literal["light", "medium", "heavy"] | None = None


class LaunchBody(BaseModel):
    name: str
    description: str = "AI-powered product"
    budget_usd: float = 450.0
    stack: str = "Next.js + Supabase + Stripe + Vercel"
    tone: str = "clean, professional"
    cycles: int = Field(default=3, ge=1, le=20)
    auto_approve: bool = True
    continuous: bool = False


class RunBody(BaseModel):
    cycles: int = Field(default=2, ge=1, le=20)
    auto_approve: bool = False


class ApproveBody(BaseModel):
    approval_id: str
    approve: bool = True
    option_index: int | None = None
    note: str = ""


# ── Meta / setup ─────────────────────────────────────────────


@router.get("/meta")
def meta() -> dict[str, Any]:
    cfg = load_user_config()
    return {
        "version": __version__,
        "setup_completed": cfg.setup_completed,
        "data_dir": str(get_settings().data_dir),
    }


@router.get("/config")
def get_config() -> dict[str, Any]:
    cfg = load_user_config()
    return cfg.model_dump()


@router.post("/config")
def post_config(body: SaveConfigBody) -> dict[str, Any]:
    cfg = UserConfig(
        models=body.models,
        budget_alert_usd=body.budget_alert_usd,
        default_company_budget_usd=body.default_company_budget_usd,
        require_human_approval=body.require_human_approval,
        usage_profile=body.usage_profile,
        setup_completed=True,
    )
    path = save_user_config(cfg)
    return {"ok": True, "path": str(path), "config": cfg.model_dump()}


@router.get("/models")
def list_models() -> dict[str, Any]:
    roles = ["brain", "operator", "marketer", "accountant"]
    by_role: dict[str, list[dict[str, Any]]] = {}
    for role in roles:
        items = []
        for mid, meta in get_available_models_for_role(role):  # type: ignore[arg-type]
            ready, key = model_ready(mid)
            items.append(
                {
                    "id": mid,
                    "label": meta.get("label", mid),
                    "provider": meta.get("provider"),
                    "input_per_m": meta.get("input_per_m", 0),
                    "output_per_m": meta.get("output_per_m", 0),
                    "ready": ready,
                    "key_name": key,
                }
            )
        by_role[role] = items
    return {
        "roles": roles,
        "by_role": by_role,
        "catalog": {
            mid: {
                "label": m.get("label"),
                "provider": m.get("provider"),
                "input_per_m": m.get("input_per_m"),
                "output_per_m": m.get("output_per_m"),
                "roles": m.get("roles"),
            }
            for mid, m in MODEL_CATALOG.items()
        },
        "usage_profiles": {
            k: {"label": v["label"], "companies": v["companies"]}
            for k, v in USAGE_PROFILES.items()
        },
    }


@router.post("/costs/estimate")
def costs_estimate(body: CostEstimateBody) -> dict[str, Any]:
    if body.profile:
        return estimate_monthly_cost(body.models, body.profile)
    return {
        "profiles": {
            p: estimate_monthly_cost(body.models, p) for p in ("light", "medium", "heavy")
        }
    }


@router.get("/costs/estimate")
def costs_estimate_get(
    brain: str = "claude-sonnet-4-5",
    operator: str = "gpt-4o",
    marketer: str = "gpt-4o",
    accountant: str = "gpt-4o",
) -> dict[str, Any]:
    models = AgentModelConfig(
        brain=brain, operator=operator, marketer=marketer, accountant=accountant
    )
    return {
        "profiles": {
            p: estimate_monthly_cost(models, p) for p in ("light", "medium", "heavy")
        }
    }


# ── Companies ────────────────────────────────────────────────


@router.get("/companies")
def list_companies() -> dict[str, Any]:
    brain = _brain()
    projects = brain.list_projects()
    return {
        "companies": [
            {
                "id": p.id,
                "name": p.name,
                "slug": p.slug,
                "description": p.description,
                "status": p.status,
                "budget_usd": p.budget_usd,
                "spent_usd": p.spent_usd,
                "domain": p.domain,
                "github_repo": p.github_repo,
                "vercel_url": p.vercel_url,
                "created_at": p.created_at.isoformat(),
            }
            for p in projects
        ]
    }


@router.get("/companies/{slug}")
def get_company(slug: str) -> dict[str, Any]:
    brain = _brain()
    p = brain.get_project(slug) or brain.get_project_by_slug(slug)
    if not p:
        raise HTTPException(404, f"Company not found: {slug}")

    snap = brain.budget_snapshot(p.id)
    agents = brain.get_agent_statuses(p.id)
    messages = brain.get_thread(p.id, limit=40)
    domains = brain.list_domain_options(p.id)[:12]
    emails = brain.list_emails(p.id)
    socials = brain.list_socials(p.id)
    posts = brain.list_social_posts(p.id)[:12]
    pending = brain.list_pending_approvals(p.id)
    costs = brain.list_costs(p.id)

    return {
        "project": p.model_dump(mode="json"),
        "budget": snap.model_dump(),
        "agents": [a.model_dump(mode="json") for a in agents],
        "messages": [m.model_dump(mode="json") for m in messages],
        "domains": [d.model_dump() for d in domains],
        "emails": [e.model_dump(mode="json") for e in emails],
        "socials": [s.model_dump(mode="json") for s in socials],
        "posts": [po.model_dump(mode="json") for po in posts],
        "pending_approvals": [a.model_dump(mode="json") for a in pending],
        "costs": [c.model_dump(mode="json") for c in costs],
    }


@router.post("/companies/launch")
def launch(body: LaunchBody) -> dict[str, Any]:
    brief = CompanyBrief(
        name=body.name.strip(),
        description=body.description.strip(),
        budget_usd=body.budget_usd,
        stack_preference=body.stack,
        tone=body.tone,
    )
    if not brief.name:
        raise HTTPException(400, "Company name is required")

    context: dict[str, Any] = {}
    if body.auto_approve:
        context = {
            "auto_approve": True,
            "auto_pick_domain": True,
            "approve_domain": True,
            "approve_social": True,
        }

    job_id = f"job_{brief.name.lower().replace(' ', '-')}"
    with _jobs_lock:
        _jobs[job_id] = {"status": "running", "name": brief.name, "error": None, "result": None}

    def _run() -> None:
        try:
            result = launch_company(
                brief,
                max_cycles=body.cycles,
                context=context,
                continuous=body.continuous,
            )
            project = result.get("project")
            with _jobs_lock:
                _jobs[job_id] = {
                    "status": "done",
                    "name": brief.name,
                    "error": None,
                    "result": {
                        "project_id": project.get("id") if project else None,
                        "slug": project.get("slug") if project else None,
                        "status": project.get("status") if project else None,
                        "domain": project.get("domain") if project else None,
                        "vercel_url": project.get("vercel_url") if project else None,
                        "spent_usd": project.get("spent_usd") if project else None,
                    },
                }
        except Exception as e:
            with _jobs_lock:
                _jobs[job_id] = {
                    "status": "error",
                    "name": brief.name,
                    "error": str(e),
                    "result": None,
                }

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return {"ok": True, "job_id": job_id, "message": f"Launching {brief.name}…"}


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@router.post("/companies/{slug}/run")
def run_more(slug: str, body: RunBody) -> dict[str, Any]:
    context: dict[str, Any] = {}
    if body.auto_approve:
        context = {
            "auto_approve": True,
            "approve_domain": True,
            "approve_social": True,
            "auto_pick_domain": True,
        }
    try:
        continue_company(slug, max_cycles=body.cycles, context=context)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return {"ok": True, "slug": slug, "cycles": body.cycles}


# ── Approvals ────────────────────────────────────────────────


@router.get("/approvals")
def list_approvals(project: str | None = None) -> dict[str, Any]:
    brain = _brain()
    pid = None
    if project:
        p = brain.get_project(project) or brain.get_project_by_slug(project)
        if not p:
            raise HTTPException(404, "Project not found")
        pid = p.id
    pending = brain.list_pending_approvals(pid)
    return {"approvals": [a.model_dump(mode="json") for a in pending]}


@router.post("/approvals/decide")
def decide_approval(body: ApproveBody) -> dict[str, Any]:
    brain = _brain()
    toolkit = BudgetToolkit(brain)
    appr = brain.get_approval(body.approval_id)
    if not appr:
        raise HTTPException(404, "Approval not found")

    if not body.approve:
        brain.decide_approval(body.approval_id, False, body.note or "Rejected via Web UI")
        return {"ok": True, "status": "rejected"}

    # Domain / option choice
    if appr.action == "choose_option" and appr.options:
        idx = body.option_index if body.option_index is not None else 0
        idx = max(0, min(idx, len(appr.options) - 1))
        pick = appr.options[idx]
        p = brain.get_project(appr.project_id)
        if p:
            p.metadata["selected_domain"] = pick
            p.metadata["preferred_domain"] = pick
            brain.update_project(p)
        brain.decide_approval(body.approval_id, True, body.note or f"Chose option {idx}")
        return {"ok": True, "status": "approved", "selected": pick}

    toolkit.approve_request(body.approval_id, note=body.note or "Approved via Web UI")
    return {"ok": True, "status": "approved"}
