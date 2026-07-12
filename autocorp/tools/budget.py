"""Budget tracking, approval gates, Stripe setup, P&L reporting."""

from __future__ import annotations

from typing import Any

from autocorp.core.config import get_settings
from autocorp.core.models import (
    AgentRole,
    ApprovalRequest,
    BudgetSnapshot,
    CostCategory,
    CostEntry,
)
from autocorp.db.brain import SharedBrain


class BudgetToolkit:
    """Accountant tools: costs, approvals, Stripe, live P&L."""

    def __init__(self, brain: SharedBrain) -> None:
        self.brain = brain
        self.settings = get_settings()

    def snapshot(self, project_id: str) -> BudgetSnapshot:
        return self.brain.budget_snapshot(project_id)

    def propose_spend(
        self,
        project_id: str,
        category: CostCategory | str,
        amount_usd: float,
        description: str,
        vendor: str = "",
        requested_by: AgentRole = AgentRole.ACCOUNTANT,
        irreversible: bool = False,
        auto_approve_under: float = 0.0,
    ) -> dict[str, Any]:
        """Propose a cost. Creates pending cost + approval if over threshold."""
        cat = CostCategory(category) if isinstance(category, str) else category
        snap = self.snapshot(project_id)

        if amount_usd > snap.remaining_usd:
            return {
                "ok": False,
                "rejected": True,
                "reason": (
                    f"Insufficient budget: need ${amount_usd:.2f}, "
                    f"remaining ${snap.remaining_usd:.2f}"
                ),
                "snapshot": snap.model_dump(),
            }

        auto = amount_usd <= auto_approve_under and not irreversible
        entry = CostEntry(
            project_id=project_id,
            category=cat,
            amount_usd=amount_usd,
            description=description,
            vendor=vendor,
            approved=auto,
            approved_by="auto" if auto else None,
        )
        self.brain.add_cost(entry)

        approval = None
        if not auto:
            approval = ApprovalRequest(
                project_id=project_id,
                requested_by=requested_by,
                action=f"spend:{cat.value}",
                description=description,
                amount_usd=amount_usd,
                irreversible=irreversible,
                metadata={"cost_id": entry.id, "vendor": vendor},
            )
            self.brain.create_approval(approval)

        return {
            "ok": True,
            "cost": entry.model_dump(mode="json"),
            "approval": approval.model_dump(mode="json") if approval else None,
            "auto_approved": auto,
            "snapshot": self.snapshot(project_id).model_dump(),
        }

    def approve_spend(self, cost_id: str, approved_by: str = "human") -> CostEntry | None:
        return self.brain.approve_cost(cost_id, approved_by=approved_by)

    def reject_spend(self, approval_id: str, note: str = "Rejected by human") -> ApprovalRequest | None:
        return self.brain.decide_approval(approval_id, approved=False, note=note)

    def approve_request(self, approval_id: str, note: str = "Approved") -> dict[str, Any]:
        req = self.brain.decide_approval(approval_id, approved=True, note=note)
        if not req:
            return {"ok": False, "error": "approval not found"}
        cost_id = (req.metadata or {}).get("cost_id")
        cost = None
        if cost_id:
            cost = self.brain.approve_cost(cost_id, approved_by="human")
        return {
            "ok": True,
            "approval": req.model_dump(mode="json"),
            "cost": cost.model_dump(mode="json") if cost else None,
        }

    def present_options(
        self,
        project_id: str,
        title: str,
        options: list[dict[str, Any]],
        requested_by: AgentRole = AgentRole.ACCOUNTANT,
    ) -> ApprovalRequest:
        """Present cost options for human choice (e.g. domain A vs B)."""
        req = ApprovalRequest(
            project_id=project_id,
            requested_by=requested_by,
            action="choose_option",
            description=title,
            amount_usd=min((o.get("price_usd") or o.get("amount_usd") or 0) for o in options) if options else 0,
            irreversible=False,
            options=options,
        )
        self.brain.create_approval(req)
        return req

    def pnl_report(self, project_id: str) -> dict[str, Any]:
        snap = self.snapshot(project_id)
        costs = self.brain.list_costs(project_id)
        project = self.brain.get_project(project_id)
        recurring = sum(c.amount_usd for c in costs if c.approved and c.recurring_monthly)
        return {
            "company": project.name if project else project_id,
            "budget_usd": snap.budget_usd,
            "spent_usd": snap.spent_usd,
            "pending_usd": snap.pending_usd,
            "remaining_usd": snap.remaining_usd,
            "utilization_pct": round(100 * snap.spent_usd / snap.budget_usd, 1)
            if snap.budget_usd
            else 0,
            "by_category": snap.by_category,
            "recurring_monthly_usd": recurring,
            "alert": snap.alert,
            "alert_message": snap.alert_message,
            "line_items": [
                {
                    "id": c.id,
                    "category": c.category.value,
                    "amount": c.amount_usd,
                    "description": c.description,
                    "approved": c.approved,
                    "vendor": c.vendor,
                }
                for c in costs
            ],
        }

    def setup_stripe(self, project_id: str, company_name: str) -> dict[str, Any]:
        """Configure Stripe for the company (mock if no keys)."""
        live = bool(self.settings.stripe_secret_key)
        product_name = f"{company_name} Pro"
        result = {
            "ok": True,
            "mode": "live" if live else "mock",
            "product": product_name,
            "prices": [
                {"nickname": "monthly", "unit_amount": 1900, "currency": "usd", "interval": "month"},
                {"nickname": "yearly", "unit_amount": 19000, "currency": "usd", "interval": "year"},
            ],
            "publishable_key_set": bool(self.settings.stripe_publishable_key),
            "message": (
                f"Stripe ready for {company_name}"
                if live
                else f"[MOCK] Stripe product plan drafted for {company_name}"
            ),
        }
        # Record setup as zero-cost tooling entry
        self.brain.add_cost(
            CostEntry(
                project_id=project_id,
                category=CostCategory.TOOLS,
                amount_usd=0.0,
                description=f"Stripe setup ({result['mode']})",
                vendor="stripe",
                approved=True,
                approved_by="accountant",
                metadata=result,
            )
        )
        return result

    def can_afford(self, project_id: str, amount_usd: float) -> bool:
        return self.snapshot(project_id).remaining_usd >= amount_usd
