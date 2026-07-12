"""Vercel deployment helpers for The Brain."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import httpx

from autocorp.core.config import get_settings


class VercelToolkit:
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def configured(self) -> bool:
        return bool(self.settings.vercel_token)

    def cli_available(self) -> bool:
        return shutil.which("vercel") is not None

    def deploy(
        self,
        project_path: Path,
        project_name: str,
        prod: bool = True,
    ) -> dict[str, Any]:
        project_path = Path(project_path)
        if not project_path.exists():
            return {"ok": False, "error": f"Path not found: {project_path}"}

        # Prefer CLI when token + vercel binary available
        if self.cli_available() and self.configured:
            return self._deploy_cli(project_path, project_name, prod)

        if self.configured:
            return self._deploy_api_stub(project_name)

        slug = project_name.lower().replace(" ", "-")
        return {
            "ok": True,
            "mode": "mock",
            "url": f"https://{slug}.vercel.app",
            "message": "[MOCK] Deployed to Vercel (set VERCEL_TOKEN + install Vercel CLI for live)",
        }

    def _deploy_cli(self, path: Path, name: str, prod: bool) -> dict[str, Any]:
        env = {
            **dict(**{k: v for k, v in __import__("os").environ.items()}),
            "VERCEL_TOKEN": self.settings.vercel_token,
        }
        if self.settings.vercel_team_id:
            env["VERCEL_ORG_ID"] = self.settings.vercel_team_id

        cmd = ["vercel", "--yes", "--name", name]
        if prod:
            cmd.append("--prod")
        cmd.extend(["--token", self.settings.vercel_token])

        try:
            r = subprocess.run(
                cmd,
                cwd=str(path),
                capture_output=True,
                text=True,
                env=env,
                timeout=300,
            )
            url = ""
            for line in (r.stdout or "").splitlines():
                if "https://" in line and "vercel.app" in line:
                    url = line.strip().split()[-1]
            if not url and r.stdout:
                # last non-empty line often is the URL
                lines = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
                if lines:
                    url = lines[-1]
            return {
                "ok": r.returncode == 0,
                "mode": "live",
                "url": url or f"https://{name}.vercel.app",
                "stdout": r.stdout[-2000:] if r.stdout else "",
                "stderr": r.stderr[-1000:] if r.stderr else "",
                "message": f"Vercel deploy {'ok' if r.returncode == 0 else 'failed'}",
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _deploy_api_stub(self, name: str) -> dict[str, Any]:
        """Create/link project via REST when CLI missing."""
        headers = {
            "Authorization": f"Bearer {self.settings.vercel_token}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=30.0) as client:
                payload: dict[str, Any] = {"name": name}
                if self.settings.vercel_team_id:
                    # team projects use query param
                    pass
                params = {}
                if self.settings.vercel_team_id:
                    params["teamId"] = self.settings.vercel_team_id
                r = client.post(
                    "https://api.vercel.com/v10/projects",
                    headers=headers,
                    params=params,
                    json=payload,
                )
                data = r.json() if r.content else {}
                if r.status_code in (200, 201):
                    return {
                        "ok": True,
                        "mode": "live-project",
                        "url": f"https://{name}.vercel.app",
                        "project": data,
                        "message": "Vercel project created (deploy files via CLI for full build)",
                    }
                # already exists
                if r.status_code == 409 or "already" in json.dumps(data).lower():
                    return {
                        "ok": True,
                        "mode": "live-existing",
                        "url": f"https://{name}.vercel.app",
                        "message": "Vercel project already exists",
                    }
                return {"ok": False, "error": data, "status": r.status_code}
        except Exception as e:
            return {"ok": False, "error": str(e)}
