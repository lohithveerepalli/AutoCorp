"""Accountant — budget, approvals, Stripe, live P&L."""

from __future__ import annotations

from typing import Any

from autocorp.agents.base import BaseAgent
from autocorp.core.models import AgentRole, AgentStatus, ApprovalStatus
from autocorp.tools.budget import BudgetToolkit
from autocorp.ui.console import print_budget_table


class AccountantAgent(BaseAgent):
    role = AgentRole.ACCOUNTANT
    system_prompt = """You are The Accountant of AutoCorp — CFO.
You track every dollar against the company budget, present cost options,
approve or reject spend proposals within policy, set up Stripe,
and report live P&L. Money and irreversible actions require human approval
when configured. Be precise with numbers. Never exceed remaining budget."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.budget = BudgetToolkit(self.brain)

    def run_once(self, project_id: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        context = context or {}
        project = self.brain.get_project(project_id)
        if not project:
            return {"ok": False, "error": "project not found"}

        loop = self.brain.bump_loop(project_id, self.role, task="finance cycle")
        inbox = self.process_inbox(project_id)
        phase = project.metadata.get("accountant_phase", "bootstrap")
        result: dict[str, Any] = {"agent": "accountant", "loop": loop, "phase": phase}

        self.ui.panel(f"Loop #{loop} · phase={phase}", title="Accountant online")

        if phase == "bootstrap":
            result.update(self._phase_bootstrap(project))
            project = self.brain.get_project(project_id)
            project.metadata["accountant_phase"] = "review"
            self.brain.update_project(project)
        elif phase == "review":
            result.update(self._phase_review(project, inbox, context))
        else:
            result.update(self._phase_report(project))

        # Always emit live P&L snapshot in UI
        snap = self.budget.snapshot(project_id)
        print_budget_table(snap)
        result["snapshot"] = snap.model_dump()

        self.set_status(project_id, AgentStatus.IDLE, task=f"completed {phase}")
        return result

    def _phase_bootstrap(self, project) -> dict[str, Any]:
        self.ui.task("Opening books + Stripe…")
        stripe = self.budget.setup_stripe(project.id, project.name)
        self.ui.success(stripe.get("message", "Stripe configured"))

        self.say(
            project.id,
            "all",
            "Books open",
            f"Budget ${project.budget_usd:.2f}. Stripe mode={stripe.get('mode')}. "
            "All spend requires approval unless under auto-threshold.",
            priority="high",
        )
        self.say(
            project.id,
            AgentRole.OPERATOR,
            "Domain budget guidance",
            f"Recommend domain spend ≤ ${min(40, project.budget_usd * 0.15):.2f} "
            f"({min(15, 100):.0f}% guidance). Keep hosting on free tiers first.",
        )
        self.say(
            project.id,
            AgentRole.MARKETER,
            "Marketing budget guidance",
            "Organic only at launch. Propose ads only after product URL is live.",
        )
        return {"stripe": stripe}

    def _phase_review(self, project, inbox: list[str], context: dict[str, Any]) -> dict[str, Any]:
        self.ui.task("Reviewing spend proposals and domain options…")

        # Present domain options from Operator if present
        candidates = project.metadata.get("domain_candidates") or []
        if candidates and not project.domain and not project.metadata.get("domain_choice_presented"):
            req = self.budget.present_options(
                project_id=project.id,
                title=f"Choose domain for {project.name}",
                options=candidates,
                requested_by=AgentRole.ACCOUNTANT,
            )
            project.metadata["domain_choice_presented"] = True
            project.metadata["domain_choice_approval_id"] = req.id
            self.brain.update_project(project)
            self.ui.warn(f"Domain choice pending human decision ({len(candidates)} options)")
            self.say(
                project.id,
                AgentRole.HUMAN,
                "Choose a domain (budget decision)",
                f"Approval {req.id}: pick one of {len(candidates)} domain options. "
                f"Cheapest: {candidates[0].get('label')}. "
                f"autocorp approve --project {project.slug}",
                payload={"approval_id": req.id, "options": candidates},
                priority="critical",
                requires_reply=True,
            )

        # Handle auto-approve from context
        if context.get("auto_approve"):
            for appr in self.brain.list_pending_approvals(project.id):
                self.budget.approve_request(appr.id, note="Auto-approved in demo mode")
                # If domain option choice, set selected domain
                if appr.action == "choose_option" and appr.options:
                    pick = appr.options[0]
                    project.metadata["selected_domain"] = pick
                    project.metadata["preferred_domain"] = pick
                    self.brain.update_project(project)
                    self.ui.success(f"Auto-selected domain option: {pick.get('domain')}")
                if appr.action.startswith("spend:domain") or (
                    appr.metadata and "domain" in str(appr.metadata)
                ):
                    pass
            # Also approve pending domain spend and execute via operator flags
            context["approve_domain"] = True

        pending = self.brain.list_pending_approvals(project.id)
        for p in pending:
            self.ui.warn(
                f"PENDING ${p.amount_usd:.2f} — {p.action}: {p.description[:60]} "
                f"[{p.id}]"
            )

        # Policy checks
        snap = self.budget.snapshot(project.id)
        if snap.alert:
            self.ui.error(snap.alert_message)
            self.say(
                project.id,
                "all",
                "BUDGET ALERT",
                snap.alert_message,
                priority="critical",
            )

        # After first review, move to continuous reporting
        if project.metadata.get("domain_choice_presented") or project.domain:
            project.metadata["accountant_phase"] = "report"
            self.brain.update_project(project)

        return {"pending_approvals": len(pending), "inbox": len(inbox)}

    def _phase_report(self, project) -> dict[str, Any]:
        self.ui.task("Publishing live P&L…")
        report = self.budget.pnl_report(project.id)
        self.ui.success(
            f"P&L: spent ${report['spent_usd']:.2f} / ${report['budget_usd']:.2f} "
            f"({report['utilization_pct']}%) · remaining ${report['remaining_usd']:.2f}"
        )
        self.say(
            project.id,
            "all",
            "P&L update",
            f"Spent ${report['spent_usd']:.2f} · Pending ${report['pending_usd']:.2f} · "
            f"Remaining ${report['remaining_usd']:.2f} · Categories: {report['by_category']}",
        )
        return {"pnl": report}
