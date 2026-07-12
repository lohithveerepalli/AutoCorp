"""Marketer — social accounts, branding, content, growth."""

from __future__ import annotations

from typing import Any

from autocorp.agents.base import BaseAgent
from autocorp.core.models import AgentRole, AgentStatus, CostCategory
from autocorp.tools.budget import BudgetToolkit
from autocorp.tools.social import SocialToolkit


class MarketerAgent(BaseAgent):
    role = AgentRole.MARKETER
    system_prompt = """You are The Marketer of AutoCorp — CMO.
You create and manage social accounts (X, LinkedIn, Instagram, TikTok),
branding, content calendars, posting, and growth loops.
Never create live social accounts without human approval.
Prefer strong mock mode when credentials or approval are missing.
Match the company's tone exactly."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.social = SocialToolkit(self.brain)
        self.budget = BudgetToolkit(self.brain)

    def run_once(self, project_id: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        context = context or {}
        project = self.brain.get_project(project_id)
        if not project:
            return {"ok": False, "error": "project not found"}

        loop = self.brain.bump_loop(project_id, self.role, task="growth cycle")
        inbox = self.process_inbox(project_id)
        phase = project.metadata.get("marketer_phase", "brand")
        result: dict[str, Any] = {"agent": "marketer", "loop": loop, "phase": phase}

        self.ui.panel(f"Loop #{loop} · phase={phase}", title="Marketer online")

        if phase == "brand":
            result.update(self._phase_brand(project))
            project = self.brain.get_project(project_id)
            project.metadata["marketer_phase"] = "accounts"
            self.brain.update_project(project)
        elif phase == "accounts":
            result.update(self._phase_accounts(project, context))
            project = self.brain.get_project(project_id)
            # advance after presenting or creating
            if project.metadata.get("socials_ready"):
                project.metadata["marketer_phase"] = "content"
                self.brain.update_project(project)
        elif phase == "content":
            result.update(self._phase_content(project))
            project = self.brain.get_project(project_id)
            project.metadata["marketer_phase"] = "growth"
            self.brain.update_project(project)
        else:
            result.update(self._phase_growth(project, inbox))

        self.set_status(project_id, AgentStatus.IDLE, task=f"completed {phase}")
        return result

    def _phase_brand(self, project) -> dict[str, Any]:
        self.ui.task("Building brand kit…")
        kit = self.social.brand_kit(project.name, project.description, project.tone)
        project.metadata["brand_kit"] = kit
        self.brain.update_project(project)
        self.ui.success(f"Handle base: @{kit['handle_base']} · bio set")
        self.ui.log(f"Palette: {kit['palette']}")

        # LLM polish optional tagline
        polish = self.think(
            f"Write one punchy tagline (max 12 words) for {project.name}: {project.description}. "
            f"Tone: {project.tone}."
        )
        if polish:
            kit["tagline"] = polish.strip().split("\n")[0][:120]
            project.metadata["brand_kit"] = kit
            self.brain.update_project(project)
            self.ui.log(f"Tagline: {kit['tagline']}")

        self.say(
            project.id,
            AgentRole.BRAIN,
            "Brand kit ready",
            f"Handle @{kit['handle_base']}. Tagline: {kit.get('tagline')}",
        )
        return {"brand_kit": kit}

    def _phase_accounts(self, project, context: dict[str, Any]) -> dict[str, Any]:
        self.ui.task("Planning social accounts (approval required for live creation)…")
        plan = self.social.plan_accounts(project.name, project.description, project.tone)
        for p in plan:
            self.ui.log(f"{p['platform']}: {p['handle']} → {p['url']}")

        approved = bool(context.get("approve_social") or context.get("auto_approve"))
        if not approved:
            # Request human approval
            from autocorp.core.models import ApprovalRequest

            req = ApprovalRequest(
                project_id=project.id,
                requested_by=AgentRole.MARKETER,
                action="create_social_accounts",
                description=(
                    f"Create social accounts for {project.name} on "
                    f"{', '.join(p['platform'] for p in plan)}. "
                    "Without approval, mock accounts will be registered only."
                ),
                amount_usd=0.0,
                irreversible=True,
                options=plan,
            )
            self.brain.create_approval(req)
            self.set_status(project.id, AgentStatus.WAITING_APPROVAL, task="approve socials")
            self.ui.warn("Awaiting human approval for social account creation")
            self.say(
                project.id,
                AgentRole.HUMAN,
                "Approve social account creation",
                req.description + f"\nUse: autocorp approve --project {project.slug}",
                payload={"approval_id": req.id, "plan": plan},
                priority="high",
                requires_reply=True,
            )
            # Still create pending records so CEO sees the plan
            accounts = self.social.create_accounts(
                project.id,
                project.name,
                project.description,
                project.tone,
                approved=False,
            )
        else:
            accounts = self.social.create_accounts(
                project.id,
                project.name,
                project.description,
                project.tone,
                approved=True,
            )
            for a in accounts:
                self.ui.success(f"{a.platform}: {a.handle} [{a.status}]")

        project.metadata["socials_ready"] = True
        self.brain.update_project(project)
        return {
            "accounts": [
                {"platform": a.platform, "handle": a.handle, "status": a.status} for a in accounts
            ]
        }

    def _phase_content(self, project) -> dict[str, Any]:
        self.ui.task("Drafting launch content…")
        posts = self.social.draft_launch_content(
            project.name,
            project.description,
            domain=project.domain,
            tone=project.tone,
        )
        # Optional LLM rewrite for brand voice
        for p in posts:
            better = self.think(
                f"Rewrite this {p['platform']} post in tone '{project.tone}' "
                f"for {project.name}. Keep platform length limits. Return only the post text:\n\n"
                f"{p['content']}"
            )
            if better and len(better) > 20:
                p["content"] = better.strip()[:1000 if p["platform"] != "x" else 280]

        created = self.social.schedule_posts(project.id, posts, status="draft")
        for p in created:
            self.ui.log(f"[{p.platform}] {p.content[:70]}…")

        self.say(
            project.id,
            AgentRole.BRAIN,
            "Launch content drafted",
            f"{len(created)} posts ready as drafts. Production URL: {project.vercel_url or 'pending'}",
        )
        self.say(
            project.id,
            AgentRole.ACCOUNTANT,
            "No ad spend yet",
            "Organic launch only. Ad budget can be proposed later.",
        )
        return {"posts": len(created)}

    def _phase_growth(self, project, inbox: list[str]) -> dict[str, Any]:
        self.ui.task("Growth loop…")
        plan = self.social.growth_plan(project.name, project.description)
        socials = self.brain.list_socials(project.id)
        posts = self.brain.list_social_posts(project.id)
        self.ui.log(f"Accounts={len(socials)} · Posts={len(posts)} · KPIs={plan['kpis']}")

        # Propose zero-cost organic growth; ads need approval
        if project.metadata.get("propose_ads"):
            self.budget.propose_spend(
                project_id=project.id,
                category=CostCategory.SOCIAL_ADS,
                amount_usd=50.0,
                description="Optional launch ad boost (X + LinkedIn)",
                vendor="meta/x",
                requested_by=AgentRole.MARKETER,
                irreversible=False,
            )

        if inbox:
            self.say(
                project.id,
                AgentRole.BRAIN,
                "Growth feedback",
                f"Marketing active. {len(posts)} content pieces. Week-1 plan in motion.",
            )
        self.ui.success("Growth plan ticking")
        return {"growth": plan, "socials": len(socials), "posts": len(posts)}
