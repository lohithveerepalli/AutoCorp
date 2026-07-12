"""Brain (Claude) — full product ownership: research, architecture, code, deploy."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from autocorp.agents.base import BaseAgent
from autocorp.core.config import get_settings
from autocorp.core.models import AgentRole, AgentStatus, CostCategory
from autocorp.tools.github_tools import GitHubToolkit
from autocorp.tools.supabase_tools import SupabaseToolkit
from autocorp.tools.vercel_tools import VercelToolkit


class BrainAgent(BaseAgent):
    role = AgentRole.BRAIN
    system_prompt = """You are The Brain of AutoCorp — CTO and full product owner.
You research, architect, write all application code, create the GitHub repo,
configure Supabase, deploy to Vercel, and iterate on feedback from Operator,
Marketer, and Accountant. Prefer clean, production-ready Next.js code.
Always respect budget constraints from the Accountant. Never spend money yourself —
request approval via the Accountant for paid services."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.github = GitHubToolkit()
        self.vercel = VercelToolkit()
        self.supabase = SupabaseToolkit()
        self.settings = get_settings()

    def run_once(self, project_id: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        context = context or {}
        project = self.brain.get_project(project_id)
        if not project:
            return {"ok": False, "error": "project not found"}

        loop = self.brain.bump_loop(project_id, self.role, task="product cycle")
        inbox = self.process_inbox(project_id)
        phase = project.metadata.get("brain_phase", "scaffold")
        result: dict[str, Any] = {"agent": "brain", "loop": loop, "phase": phase, "inbox": inbox}

        self.ui.panel(
            f"Loop #{loop} · phase={phase}\n{project.name}: {project.description[:100]}",
            title="Brain online",
        )

        if phase == "scaffold":
            result.update(self._phase_scaffold(project))
            project = self.brain.get_project(project_id)  # refresh
            project.metadata["brain_phase"] = "infra"
            self.brain.update_project(project)
        elif phase == "infra":
            result.update(self._phase_infra(project))
            project = self.brain.get_project(project_id)
            project.metadata["brain_phase"] = "deploy"
            self.brain.update_project(project)
        elif phase == "deploy":
            result.update(self._phase_deploy(project))
            project = self.brain.get_project(project_id)
            project.metadata["brain_phase"] = "iterate"
            project.status = "active"
            self.brain.update_project(project)
        else:
            result.update(self._phase_iterate(project, inbox))

        self.set_status(project_id, AgentStatus.IDLE, task=f"completed {phase}")
        return result

    def _phase_scaffold(self, project) -> dict[str, Any]:
        self.ui.task("Scaffolding product codebase…")
        domain = project.domain
        files = self.github.scaffold_nextjs_app(
            company_name=project.name,
            description=project.description,
            tone=project.tone,
            domain=domain,
        )

        # Optional LLM polish for architecture note
        arch = self.think(
            f"Write a short architecture note (max 200 words) for {project.name}: "
            f"{project.description}. Stack: {project.stack}. Tone: {project.tone}."
        )
        if arch:
            files["docs/ARCHITECTURE.md"] = f"# Architecture\n\n{arch}\n"

        data_dir = self.settings.data_dir / "companies" / project.slug
        local = self.github.write_files_local(data_dir / "app", files)
        self.ui.success(f"Wrote {len(files)} files → {local}")

        repo = self.github.create_repo(
            name=project.slug,
            description=project.description,
            private=False,
        )
        if repo.get("ok"):
            project.github_repo = repo.get("full_name")
            self.brain.update_project(project)
            self.ui.success(f"GitHub: {repo.get('html_url')} ({repo.get('mode')})")
            push = self.github.init_and_push(
                local,
                repo.get("clone_url") or "",
                commit_message=f"feat: initial {project.name} scaffold by AutoCorp Brain",
            )
            self.ui.log(push.get("message", ""))
        else:
            self.ui.error(f"GitHub failed: {repo.get('error')}")

        self.say(
            project.id,
            AgentRole.OPERATOR,
            "Code scaffold ready",
            f"Repo {project.github_repo or local} is ready. Please finalize domain + email DNS if needed.",
        )
        self.say(
            project.id,
            AgentRole.MARKETER,
            "Product landing scaffolded",
            f"{project.name} landing page ready. Brand + socials can point to repo/demo soon.",
        )
        self.say(
            project.id,
            AgentRole.ACCOUNTANT,
            "Hosting costs upcoming",
            "Vercel hobby + Supabase free tier planned ($0). Domain spend is Operator's request.",
        )
        return {"scaffold": True, "files": len(files), "repo": repo}

    def _phase_infra(self, project) -> dict[str, Any]:
        self.ui.task("Provisioning Supabase…")
        sb = self.supabase.create_project(project.name)
        if sb.get("ok"):
            project.supabase_project_id = str(sb.get("project_id"))
            project.metadata["supabase"] = {
                k: sb.get(k) for k in ("url", "mode", "project_id", "message")
            }
            self.brain.update_project(project)
            self.ui.success(sb.get("message", "Supabase ready"))

            # Persist schema file
            schema_path = (
                self.settings.data_dir / "companies" / project.slug / "app" / "supabase" / "schema.sql"
            )
            schema_path.parent.mkdir(parents=True, exist_ok=True)
            schema_path.write_text(self.supabase.sql_schema_starter(), encoding="utf-8")
        else:
            self.ui.error(str(sb.get("error")))

        self.say(
            project.id,
            "all",
            "Supabase provisioned",
            f"Supabase {sb.get('mode')}: {sb.get('url') or sb.get('error')}",
        )
        return {"supabase": sb}

    def _phase_deploy(self, project) -> dict[str, Any]:
        self.ui.task("Deploying to Vercel production…")
        app_path = self.settings.data_dir / "companies" / project.slug / "app"
        deploy = self.vercel.deploy(app_path, project.slug, prod=True)
        if deploy.get("ok"):
            project.vercel_url = deploy.get("url")
            self.brain.update_project(project)
            self.ui.success(f"Live: {project.vercel_url} ({deploy.get('mode')})")
        else:
            self.ui.error(str(deploy.get("error")))

        self.say(
            project.id,
            AgentRole.MARKETER,
            "Production URL ready",
            f"Ship marketing to {project.vercel_url or 'pending URL'}",
            priority="high",
        )
        self.say(
            project.id,
            AgentRole.ACCOUNTANT,
            "Deploy complete",
            f"Vercel deploy mode={deploy.get('mode')} — typically $0 on hobby tier.",
        )
        return {"deploy": deploy}

    def _phase_iterate(self, project, inbox: list[str]) -> dict[str, Any]:
        self.ui.task("Iteration loop — reading team feedback…")
        notes = inbox or ["No new messages; polishing docs and backlog."]
        # Lightweight continuous improvement
        backlog_path = (
            self.settings.data_dir / "companies" / project.slug / "app" / "docs" / "BACKLOG.md"
        )
        backlog_path.parent.mkdir(parents=True, exist_ok=True)
        from datetime import datetime, timezone

        stamp = datetime.now(timezone.utc).isoformat()
        entry = f"\n## Loop update {stamp}\n" + "\n".join(f"- {n}" for n in notes) + "\n"
        prev = backlog_path.read_text(encoding="utf-8") if backlog_path.exists() else "# Backlog\n"
        backlog_path.write_text(prev + entry, encoding="utf-8")

        if inbox:
            thought = self.think(
                f"Given this team feedback for {project.name}, list 3 concrete next engineering tasks:\n"
                + "\n".join(notes)
            )
            if thought:
                self.ui.log(thought[:300])
                self.say(project.id, "all", "Brain iteration plan", thought[:1500])

        self.ui.success("Iteration recorded")
        return {"iterate": True, "inbox_count": len(inbox)}
