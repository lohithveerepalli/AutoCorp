"""Supabase project setup helpers for The Brain."""

from __future__ import annotations

from typing import Any

import httpx

from autocorp.core.config import get_settings


class SupabaseToolkit:
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def configured(self) -> bool:
        return bool(self.settings.supabase_access_token)

    def create_project(
        self,
        name: str,
        region: str = "us-east-1",
        db_password: str | None = None,
    ) -> dict[str, Any]:
        if not self.configured:
            slug = name.lower().replace(" ", "-")
            return {
                "ok": True,
                "mode": "mock",
                "project_id": f"mock_{slug[:12]}",
                "url": f"https://{slug}.supabase.co",
                "message": "[MOCK] Supabase project (set SUPABASE_ACCESS_TOKEN for live)",
                "anon_key": "mock-anon-key",
                "service_role_key": "mock-service-role",
            }

        password = db_password or "AutoCorp_" + name.replace(" ", "")[:8] + "_ChangeMe1"
        headers = {
            "Authorization": f"Bearer {self.settings.supabase_access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "name": name,
            "organization_id": self.settings.supabase_org_id,
            "region": region,
            "db_pass": password,
            "plan": "free",
        }
        if not self.settings.supabase_org_id:
            return {
                "ok": False,
                "error": "SUPABASE_ORG_ID required for live project creation",
            }
        try:
            with httpx.Client(timeout=60.0) as client:
                r = client.post(
                    "https://api.supabase.com/v1/projects",
                    headers=headers,
                    json=payload,
                )
                data = r.json() if r.content else {}
                if r.status_code in (200, 201):
                    ref = data.get("id") or data.get("ref")
                    return {
                        "ok": True,
                        "mode": "live",
                        "project_id": ref,
                        "url": f"https://{ref}.supabase.co",
                        "raw": data,
                        "message": f"Supabase project created: {ref}",
                    }
                return {"ok": False, "error": data, "status": r.status_code}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def sql_schema_starter(self) -> str:
        return """-- AutoCorp starter schema
create table if not exists profiles (
  id uuid primary key references auth.users on delete cascade,
  email text,
  full_name text,
  created_at timestamptz default now()
);

create table if not exists focus_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references profiles(id) on delete cascade,
  duration_minutes int not null default 25,
  notes text,
  started_at timestamptz default now(),
  completed_at timestamptz
);

create table if not exists waitlist (
  id uuid primary key default gen_random_uuid(),
  email text unique not null,
  created_at timestamptz default now()
);

alter table profiles enable row level security;
alter table focus_sessions enable row level security;
alter table waitlist enable row level security;
"""
