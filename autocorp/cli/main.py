"""AutoCorp CLI — launch companies, setup models, approve spend, monitor agents."""

from __future__ import annotations

import json
from typing import Optional

import typer
from rich.prompt import Confirm, IntPrompt, Prompt

from autocorp import __version__
from autocorp.core.config import get_settings, load_user_config
from autocorp.core.graph import continue_company, launch_company
from autocorp.core.models import CompanyBrief
from autocorp.db.brain import SharedBrain
from autocorp.tools.budget import BudgetToolkit
from autocorp.ui.console import (
    banner,
    get_console,
    print_agent_status,
    print_budget_table,
    print_domain_options,
    print_messages,
)
from autocorp.ui.setup_wizard import run_setup_wizard

app = typer.Typer(
    name="autocorp",
    help="AutoCorp — Fully autonomous multi-agent AI Company Operating System",
    add_completion=False,
    no_args_is_help=True,
    rich_markup_mode="rich",
)


def _brain() -> SharedBrain:
    return SharedBrain(get_settings().db_path)


def _version_callback(value: bool) -> None:
    if value:
        get_console().print(f"AutoCorp v{__version__}")
        raise typer.Exit()


@app.callback()
def main_callback(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Show version and exit",
        is_eager=True,
        callback=_version_callback,
    ),
) -> None:
    """AutoCorp multi-agent company OS."""
    pass


@app.command("setup")
def setup_cmd(
    force: bool = typer.Option(False, "--force", "-f", help="Re-run even if setup completed"),
) -> None:
    """Interactive model selection, cost estimates, budget alerts, save config."""
    run_setup_wizard(force=force)


@app.command("launch")
def launch_cmd(
    name: str = typer.Argument(..., help='Company name, e.g. "FocusFlow"'),
    budget: float = typer.Option(450.0, "--budget", "-b", help="Launch budget in USD"),
    desc: str = typer.Option(
        "",
        "--desc",
        "-d",
        help="Company description",
    ),
    stack: str = typer.Option(
        "Next.js + Supabase + Stripe + Vercel",
        "--stack",
        "-s",
        help="Preferred tech stack",
    ),
    tone: str = typer.Option(
        "clean, professional",
        "--tone",
        "-t",
        help="Brand tone",
    ),
    cycles: int = typer.Option(4, "--cycles", "-c", help="Autonomous cycles to run"),
    continuous: bool = typer.Option(
        False,
        "--continuous",
        help="Keep agents looping (Ctrl+C to stop)",
    ),
    auto_approve: bool = typer.Option(
        False,
        "--auto-approve",
        help="Demo mode: auto-approve money & irreversible actions",
    ),
    skip_setup_check: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip setup prompt if config missing",
    ),
) -> None:
    """
    One-command company launcher.

    Example:
      autocorp launch "FocusFlow" --budget 450 \\
        --desc "AI Pomodoro + deep work tracker for freelancers"
    """
    console = get_console()
    cfg = load_user_config()

    if not cfg.setup_completed and not skip_setup_check:
        console.print("[yellow]First run detected — launching setup wizard…[/yellow]\n")
        cfg = run_setup_wizard()
        console.print()

    if not desc:
        desc = Prompt.ask("Company description", default="AI-powered product")

    if budget <= 0:
        budget = cfg.default_company_budget_usd

    brief = CompanyBrief(
        name=name,
        description=desc,
        budget_usd=budget,
        stack_preference=stack,
        tone=tone,
    )

    context = {}
    if auto_approve:
        context = {
            "auto_approve": True,
            "auto_pick_domain": True,
            "approve_domain": True,
            "approve_social": True,
        }
        console.print("[yellow]Demo mode: auto-approving spend & socials[/yellow]\n")

    result = launch_company(
        brief,
        max_cycles=cycles,
        context=context,
        continuous=continuous,
    )
    project = result.get("project") or {}
    if project.get("id"):
        console.print(
            f"\n[dim]Continue later:[/dim] [cyan]autocorp run {project.get('slug') or project['id']}[/cyan]"
        )


@app.command("run")
def run_cmd(
    project: str = typer.Argument(..., help="Project id or slug"),
    cycles: int = typer.Option(2, "--cycles", "-c"),
    auto_approve: bool = typer.Option(False, "--auto-approve"),
) -> None:
    """Continue autonomous agent loops for an existing company."""
    banner()
    context = {}
    if auto_approve:
        context = {
            "auto_approve": True,
            "approve_domain": True,
            "approve_social": True,
            "auto_pick_domain": True,
        }
    try:
        continue_company(project, max_cycles=cycles, context=context)
    except ValueError as e:
        get_console().print(f"[red]{e}[/red]")
        raise typer.Exit(1)


@app.command("status")
def status_cmd(
    project: Optional[str] = typer.Argument(None, help="Project id or slug (omit for all)"),
) -> None:
    """Show project, agent status, budget, and recent messages."""
    banner()
    console = get_console()
    brain = _brain()

    if not project:
        projects = brain.list_projects()
        if not projects:
            console.print("[dim]No companies yet. Launch one with:[/dim] autocorp launch \"MyCo\"")
            return
        for p in projects:
            console.print(
                f"[cyan]{p.name}[/cyan] ({p.slug}) · {p.status} · "
                f"${p.spent_usd:.2f}/${p.budget_usd:.2f} · {p.id}"
            )
        return

    p = brain.get_project(project) or brain.get_project_by_slug(project)
    if not p:
        console.print(f"[red]Not found: {project}[/red]")
        raise typer.Exit(1)

    console.print(f"[bold]{p.name}[/bold] — {p.description}")
    console.print(
        f"Status: {p.status} · Domain: {p.domain or '—'} · "
        f"GitHub: {p.github_repo or '—'} · Vercel: {p.vercel_url or '—'}"
    )
    print_agent_status(brain.get_agent_statuses(p.id))
    print_budget_table(brain.budget_snapshot(p.id))
    domains = brain.list_domain_options(p.id)
    if domains:
        print_domain_options(domains[:8])
    msgs = brain.get_thread(p.id, limit=12)
    if msgs:
        console.print("\n[bold]Message bus[/bold]")
        print_messages(msgs)
    pending = brain.list_pending_approvals(p.id)
    if pending:
        console.print(f"\n[yellow]{len(pending)} pending approval(s)[/yellow]")


@app.command("approve")
def approve_cmd(
    project: str = typer.Option(..., "--project", "-p", help="Project id or slug"),
    all_pending: bool = typer.Option(False, "--all", help="Approve all pending"),
    reject: bool = typer.Option(False, "--reject", help="Reject instead of approve"),
) -> None:
    """Review and approve/reject money & irreversible actions."""
    console = get_console()
    brain = _brain()
    p = brain.get_project(project) or brain.get_project_by_slug(project)
    if not p:
        console.print(f"[red]Not found: {project}[/red]")
        raise typer.Exit(1)

    pending = brain.list_pending_approvals(p.id)
    if not pending:
        console.print("[green]No pending approvals.[/green]")
        return

    toolkit = BudgetToolkit(brain)

    if all_pending:
        for appr in pending:
            if reject:
                brain.decide_approval(appr.id, approved=False, note="Rejected via CLI --all")
                console.print(f"[red]Rejected[/red] {appr.id}: {appr.description[:60]}")
            else:
                toolkit.approve_request(appr.id, note="Approved via CLI --all")
                _maybe_apply_domain_choice(brain, p, appr)
                console.print(f"[green]Approved[/green] {appr.id}: {appr.description[:60]}")
        return

    for i, appr in enumerate(pending, 1):
        console.print(
            f"\n[bold]{i}/{len(pending)}[/bold] [{appr.id}] "
            f"${appr.amount_usd:.2f} — {appr.action}\n  {appr.description}"
        )
        if appr.options:
            for j, opt in enumerate(appr.options[:10], 1):
                label = opt.get("label") or json.dumps(opt)[:80]
                console.print(f"    {j}. {label}")

        if reject:
            brain.decide_approval(appr.id, False, "Rejected via CLI")
            console.print("[red]Rejected[/red]")
            continue

        if not Confirm.ask("Approve?", default=True):
            brain.decide_approval(appr.id, False, "Rejected by human")
            console.print("[red]Rejected[/red]")
            continue

        # Domain choice with options
        if appr.action == "choose_option" and appr.options:
            idx = IntPrompt.ask(
                "Option number",
                default=1,
            )
            idx = max(1, min(idx, len(appr.options))) - 1
            pick = appr.options[idx]
            p.metadata["selected_domain"] = pick
            p.metadata["preferred_domain"] = pick
            brain.update_project(p)
            brain.decide_approval(appr.id, True, f"Chose {pick}")
            console.print(f"[green]Selected[/green] {pick.get('domain') or pick}")
        else:
            toolkit.approve_request(appr.id, note="Approved by human")
            _maybe_apply_domain_choice(brain, p, appr)
            console.print("[green]Approved[/green]")

    console.print(
        f"\n[dim]Continue agents:[/dim] [cyan]autocorp run {p.slug} --cycles 2[/cyan]"
    )


def _maybe_apply_domain_choice(brain: SharedBrain, project, appr) -> None:
    if appr.action == "choose_option" and appr.options:
        pick = appr.options[0]
        project.metadata["selected_domain"] = pick
        project.metadata["preferred_domain"] = pick
        brain.update_project(project)


@app.command("pnl")
def pnl_cmd(
    project: str = typer.Argument(..., help="Project id or slug"),
) -> None:
    """Live P&L report for a company."""
    brain = _brain()
    p = brain.get_project(project) or brain.get_project_by_slug(project)
    if not p:
        get_console().print(f"[red]Not found: {project}[/red]")
        raise typer.Exit(1)
    report = BudgetToolkit(brain).pnl_report(p.id)
    print_budget_table(report)
    console = get_console()
    for item in report.get("line_items", []):
        flag = "✓" if item["approved"] else "…"
        console.print(
            f"  {flag} ${item['amount']:.2f}  {item['category']:<12} {item['description'][:50]}"
        )


@app.command("messages")
def messages_cmd(
    project: str = typer.Argument(..., help="Project id or slug"),
    limit: int = typer.Option(30, "--limit", "-n"),
) -> None:
    """Show cross-agent message bus for a company."""
    brain = _brain()
    p = brain.get_project(project) or brain.get_project_by_slug(project)
    if not p:
        get_console().print(f"[red]Not found: {project}[/red]")
        raise typer.Exit(1)
    print_messages(brain.get_thread(p.id, limit=limit), limit=limit)


@app.command("config")
def config_cmd(
    show: bool = typer.Option(True, "--show/--no-show"),
) -> None:
    """Show saved user configuration and cost estimates."""
    from autocorp.core.config import estimate_monthly_cost

    cfg = load_user_config()
    console = get_console()
    console.print_json(data=cfg.model_dump())
    est = estimate_monthly_cost(cfg.models, cfg.usage_profile)
    console.print(
        f"\nEstimated monthly LLM ({cfg.usage_profile}): "
        f"[green]${est['total_usd']:.2f}[/green]"
    )


@app.command("ui")
def ui_cmd(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host"),
    port: int = typer.Option(8787, "--port", "-p", help="Bind port"),
    open_browser: bool = typer.Option(True, "--open/--no-open", help="Open browser"),
) -> None:
    """Start the AutoCorp Web UI (CEO control plane in the browser)."""
    import webbrowser

    import uvicorn

    console = get_console()
    banner()
    url = f"http://{host}:{port}"
    console.print(f"[bold cyan]Web UI[/bold cyan] → [link={url}]{url}[/link]")
    console.print("[dim]Setup · Launch · Dashboard · Approvals · Company detail[/dim]\n")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    uvicorn.run(
        "autocorp.web.app:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
    )


@app.command("serve")
def serve_cmd(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8787, "--port", "-p"),
    open_browser: bool = typer.Option(True, "--open/--no-open"),
) -> None:
    """Alias for `autocorp ui` — start the Web UI server."""
    ui_cmd(host=host, port=port, open_browser=open_browser)


if __name__ == "__main__":
    app()
