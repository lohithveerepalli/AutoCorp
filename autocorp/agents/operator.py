"""Operator — domains, email, infrastructure."""

from __future__ import annotations

from typing import Any

from autocorp.agents.base import BaseAgent
from autocorp.core.models import AgentRole, AgentStatus, CostCategory
from autocorp.tools.budget import BudgetToolkit
from autocorp.tools.domains import DomainToolkit
from autocorp.tools.email_accounts import EmailToolkit
from autocorp.ui.console import print_domain_options


class OperatorAgent(BaseAgent):
    role = AgentRole.OPERATOR
    system_prompt = """You are The Operator of AutoCorp — infrastructure and ops lead.
You research domains across registrars, present real price alternatives within budget,
purchase domains after approval, create company and employee emails, and handle DNS/infra.
Always show alternatives with prices. Never buy without Accountant/human approval."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.domains = DomainToolkit(self.brain)
        self.email = EmailToolkit(self.brain)
        self.budget = BudgetToolkit(self.brain)

    def run_once(self, project_id: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        context = context or {}
        project = self.brain.get_project(project_id)
        if not project:
            return {"ok": False, "error": "project not found"}

        loop = self.brain.bump_loop(project_id, self.role, task="ops cycle")
        inbox = self.process_inbox(project_id)
        phase = project.metadata.get("operator_phase", "domains")
        result: dict[str, Any] = {"agent": "operator", "loop": loop, "phase": phase}

        self.ui.panel(f"Loop #{loop} · phase={phase}", title="Operator online")

        if phase == "domains":
            result.update(self._phase_domains(project, context))
            project = self.brain.get_project(project_id)
            # Only advance if domain chosen or options presented
            if project.domain or project.metadata.get("domain_options_ready"):
                project.metadata["operator_phase"] = "purchase"
                self.brain.update_project(project)
        elif phase == "purchase":
            result.update(self._phase_purchase(project, context))
            project = self.brain.get_project(project_id)
            if project.domain:
                project.metadata["operator_phase"] = "email"
                self.brain.update_project(project)
        elif phase == "email":
            result.update(self._phase_email(project))
            project = self.brain.get_project(project_id)
            project.metadata["operator_phase"] = "maintain"
            self.brain.update_project(project)
        else:
            result.update(self._phase_maintain(project, inbox))

        self.set_status(project_id, AgentStatus.IDLE, task=f"completed {phase}")
        return result

    def _phase_domains(self, project, context: dict[str, Any]) -> dict[str, Any]:
        self.ui.task("Researching domains across Porkbun, Namecheap, Cloudflare…")
        options = self.domains.research(
            project_id=project.id,
            company_name=project.name,
            description=project.description,
            max_budget=project.budget_usd * 0.25,  # cap domain at 25% budget for research filter
        )
        best = self.domains.best_options(options, budget=min(50.0, project.budget_usd), limit=8)
        print_domain_options(best)

        comparison = self.domains.compare_table(options)[:12]
        self.ui.success(f"Found {len(best)} affordable available options")

        # Ask accountant to present purchase options
        option_payload = [
            {
                "domain": o.domain,
                "registrar": o.registrar,
                "price_usd": o.price_usd,
                "renew_price_usd": o.renew_price_usd,
                "label": f"{o.domain} via {o.registrar} — ${o.price_usd:.2f}",
            }
            for o in best
        ]
        self.say(
            project.id,
            AgentRole.ACCOUNTANT,
            "Domain purchase options ready",
            f"Please present domain choices for {project.name} within budget. "
            f"Top pick: {best[0].domain if best else 'none'} "
            f"(${best[0].price_usd if best else 0:.2f}).",
            payload={"options": option_payload},
            requires_reply=True,
            priority="high",
        )
        self.say(
            project.id,
            AgentRole.BRAIN,
            "Domain research complete",
            f"{len(best)} candidates. Awaiting purchase approval.",
        )

        project.metadata["domain_options_ready"] = True
        project.metadata["domain_candidates"] = option_payload
        self.brain.update_project(project)

        # Auto-select cheapest if approval bypassed via context
        if context.get("auto_pick_domain") and best:
            project.metadata["preferred_domain"] = option_payload[0]
            self.brain.update_project(project)

        return {"options": option_payload, "best_count": len(best)}

    def _phase_purchase(self, project, context: dict[str, Any]) -> dict[str, Any]:
        # Prefer human-selected domain from context / metadata
        preferred = (
            context.get("selected_domain")
            or project.metadata.get("selected_domain")
            or project.metadata.get("preferred_domain")
        )
        candidates = project.metadata.get("domain_candidates") or []

        if not preferred and candidates:
            preferred = candidates[0]

        if not preferred:
            self.ui.warn("No domain candidate — re-running research next loop")
            project.metadata["operator_phase"] = "domains"
            self.brain.update_project(project)
            return {"purchased": False}

        domain = preferred["domain"]
        registrar = preferred["registrar"]
        price = float(preferred["price_usd"])

        self.ui.task(f"Requesting purchase of {domain} (${price:.2f} via {registrar})…")

        # Propose spend through accountant tools
        spend = self.budget.propose_spend(
            project_id=project.id,
            category=CostCategory.DOMAIN,
            amount_usd=price,
            description=f"Domain {domain} via {registrar}",
            vendor=registrar,
            requested_by=AgentRole.OPERATOR,
            irreversible=True,
            auto_approve_under=0.0,  # always need approval for domains
        )

        # If human already approved via context
        if context.get("approve_domain") or context.get("auto_approve"):
            cost_id = spend.get("cost", {}).get("id")
            approval_id = (spend.get("approval") or {}).get("id")
            if approval_id:
                self.budget.approve_request(approval_id, note="Approved for launch")
            elif cost_id:
                self.budget.approve_spend(cost_id)
            purchase = self.domains.execute_purchase(
                project.id, domain, registrar, price, dry_run=True
            )
            self.ui.success(purchase.get("message", f"Purchased {domain}"))
            self.say(
                project.id,
                "all",
                f"Domain acquired: {domain}",
                purchase.get("message", ""),
                priority="high",
            )
            return {"purchased": True, "domain": domain, "purchase": purchase}

        self.set_status(project.id, AgentStatus.WAITING_APPROVAL, task=f"approve {domain}")
        self.ui.warn(f"Waiting for human approval to buy {domain} (${price:.2f})")
        self.say(
            project.id,
            AgentRole.HUMAN,
            f"Approve domain purchase: {domain}",
            f"Buy {domain} via {registrar} for ${price:.2f}? "
            f"Use: autocorp approve --project {project.slug}",
            payload=spend,
            priority="critical",
            requires_reply=True,
        )
        return {"purchased": False, "awaiting_approval": True, "spend": spend}

    def _phase_email(self, project) -> dict[str, Any]:
        domain = project.domain
        if not domain:
            # Use placeholder domain for mock emails
            domain = f"{project.slug}.com"
            self.ui.warn(f"No purchased domain yet — using {domain} for email plan")

        self.ui.task(f"Creating company + employee emails on {domain}…")
        accounts = self.email.create_accounts(
            project_id=project.id,
            domain=domain,
            company_name=project.name,
            dry_run=True,
        )
        for a in accounts:
            self.ui.success(f"{a.address} ({a.role})")

        self.say(
            project.id,
            "all",
            "Email accounts ready",
            self.email.summary(project.id),
        )
        # Optional small email platform cost
        self.budget.propose_spend(
            project_id=project.id,
            category=CostCategory.EMAIL,
            amount_usd=0.0,
            description="Email accounts (mock / free tier)",
            vendor="mock",
            requested_by=AgentRole.OPERATOR,
            auto_approve_under=1.0,
        )
        return {"emails": [a.address for a in accounts]}

    def _phase_maintain(self, project, inbox: list[str]) -> dict[str, Any]:
        self.ui.task("Infrastructure health check…")
        emails = self.email.list_accounts(project.id)
        self.ui.log(
            f"Domain={project.domain or '—'} · Emails={len(emails)} · Inbox notes={len(inbox)}"
        )
        if inbox:
            self.say(
                project.id,
                AgentRole.BRAIN,
                "Ops status",
                f"Infra stable. Domain: {project.domain}. {len(emails)} mailboxes.",
            )
        return {"maintain": True, "emails": len(emails)}
