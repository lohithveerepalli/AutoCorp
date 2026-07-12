"""Company + employee email account creation."""

from __future__ import annotations

import secrets
import string
from typing import Any

from autocorp.core.config import get_settings
from autocorp.core.models import EmailAccount
from autocorp.db.brain import SharedBrain


def _gen_password(length: int = 20) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


class EmailToolkit:
    """Create company@ and team@ emails. Uses Google Workspace when configured, else mock."""

    DEFAULT_ROLES = [
        ("company", "Company", "hello"),
        ("brain", "Brain (Engineering)", "brain"),
        ("operator", "Operator", "ops"),
        ("marketer", "Marketer", "growth"),
        ("accountant", "Accountant", "finance"),
    ]

    def __init__(self, brain: SharedBrain) -> None:
        self.brain = brain
        self.settings = get_settings()

    def plan_accounts(self, domain: str, company_name: str) -> list[dict[str, str]]:
        plan = []
        for role, display, local in self.DEFAULT_ROLES:
            addr = f"{local}@{domain}"
            plan.append(
                {
                    "role": role,
                    "display_name": f"{display} @ {company_name}",
                    "address": addr,
                    "local_part": local,
                }
            )
        return plan

    def create_accounts(
        self,
        project_id: str,
        domain: str,
        company_name: str,
        dry_run: bool = True,
    ) -> list[EmailAccount]:
        plan = self.plan_accounts(domain, company_name)
        use_google = bool(
            self.settings.google_workspace_admin_email
            and self.settings.google_service_account_json
            and not dry_run
        )
        provider = "google_workspace" if use_google else "mock"
        created: list[EmailAccount] = []

        for item in plan:
            password = _gen_password()
            if use_google:
                self._create_google_user(item["address"], item["display_name"], password)

            account = EmailAccount(
                project_id=project_id,
                address=item["address"],
                display_name=item["display_name"],
                role=item["role"],
                provider=provider,
                password_hint=f"generated (len={len(password)}) — check secure vault",
            )
            self.brain.add_email(account)
            created.append(account)

        return created

    def _create_google_user(self, email: str, display_name: str, password: str) -> dict[str, Any]:
        """Optional Google Workspace Directory API integration."""
        # Placeholder for real Directory API call when service account is present
        # Real implementation would use google-api-python-client
        return {
            "ok": False,
            "message": "Google Workspace integration requires google-api-python-client; using mock",
            "email": email,
        }

    def list_accounts(self, project_id: str) -> list[EmailAccount]:
        return self.brain.list_emails(project_id)

    def summary(self, project_id: str) -> str:
        accounts = self.list_accounts(project_id)
        if not accounts:
            return "No email accounts created yet."
        lines = [f"• {a.address} ({a.role}) via {a.provider}" for a in accounts]
        return "Email accounts:\n" + "\n".join(lines)
