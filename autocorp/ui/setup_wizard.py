"""Interactive CLI setup: models, costs, budget alerts, save config."""

from __future__ import annotations

from typing import Any

from rich.panel import Panel
from rich.prompt import Confirm, FloatPrompt, Prompt
from rich.table import Table

from autocorp.core.config import (
    MODEL_CATALOG,
    USAGE_PROFILES,
    AgentModelConfig,
    UserConfig,
    estimate_monthly_cost,
    get_available_models_for_role,
    load_user_config,
    save_user_config,
)
from autocorp.core.llm import model_ready as llm_ready
from autocorp.ui.console import banner, get_console

ROLES = [
    ("brain", "Brain", "blue", "Product ownership, code, deploy"),
    ("operator", "Operator", "green", "Domains, email, infrastructure"),
    ("marketer", "Marketer", "magenta", "Social, branding, growth"),
    ("accountant", "Accountant", "yellow", "Budget, Stripe, P&L"),
]


def _pick_model(role: str, current: str) -> str:
    c = get_console()
    models = get_available_models_for_role(role)  # type: ignore[arg-type]
    table = Table(
        title=f"Models for {role.upper()}",
        border_style="cyan",
        show_lines=False,
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Model")
    table.add_column("Provider")
    table.add_column("In $/M", justify="right")
    table.add_column("Out $/M", justify="right")
    table.add_column("Key", justify="center")

    for i, (mid, meta) in enumerate(models, 1):
        ready, key_name = llm_ready(mid)
        key_status = "[green]✓[/green]" if ready else "[red]✗[/red]"
        marker = " [cyan]← current[/cyan]" if mid == current else ""
        table.add_row(
            str(i),
            f"{meta.get('label', mid)}{marker}",
            meta.get("provider", "?"),
            f"{meta.get('input_per_m', 0):.2f}",
            f"{meta.get('output_per_m', 0):.2f}",
            key_status,
        )
    c.print(table)
    c.print("[dim]Enter number, or paste a model id. Empty keeps current.[/dim]")

    choice = Prompt.ask(f"Select model for [bold]{role}[/bold]", default="")
    if not choice.strip():
        return current
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(models):
            return models[idx][0]
        c.print("[red]Invalid number — keeping current.[/red]")
        return current
    if choice in MODEL_CATALOG or choice.startswith("ollama/") or "/" in choice:
        return choice
    c.print("[yellow]Unknown model id — keeping current.[/yellow]")
    return current


def _show_cost_estimates(models: AgentModelConfig) -> None:
    c = get_console()
    table = Table(
        title="Estimated monthly LLM cost by usage",
        border_style="yellow",
        show_header=True,
    )
    table.add_column("Usage level")
    table.add_column("Companies")
    table.add_column("Brain", justify="right")
    table.add_column("Operator", justify="right")
    table.add_column("Marketer", justify="right")
    table.add_column("Accountant", justify="right")
    table.add_column("Total", justify="right", style="bold green")

    for profile in ("light", "medium", "heavy"):
        est = estimate_monthly_cost(models, profile)
        b = est["breakdown"]
        table.add_row(
            USAGE_PROFILES[profile]["label"],
            str(est["companies_per_month"]),
            f"${b['brain']:.2f}",
            f"${b['operator']:.2f}",
            f"${b['marketer']:.2f}",
            f"${b['accountant']:.2f}",
            f"${est['total_usd']:.2f}",
        )
    c.print(table)
    c.print(
        Panel(
            "[dim]Estimates use public list prices and typical token splits "
            "(Brain ~55% of tokens). Local Ollama models are $0. "
            "Infrastructure (domains, hosting) is tracked separately per company budget.[/dim]",
            border_style="dim",
        )
    )


def run_setup_wizard(force: bool = False) -> UserConfig:
    """Polished interactive configuration CLI."""
    c = get_console()
    banner()
    c.print(
        Panel(
            "[bold]Welcome to AutoCorp setup[/bold]\n\n"
            "Configure which models each agent uses, review estimated monthly costs,\n"
            "set budget alerts, and save defaults. You can re-run anytime with "
            "[cyan]autocorp setup[/cyan].",
            border_style="cyan",
            title="⚙️  Setup Wizard",
        )
    )

    config = load_user_config()
    if config.setup_completed and not force:
        if not Confirm.ask(
            "Setup already completed. Reconfigure?",
            default=False,
        ):
            c.print("[dim]Keeping existing configuration.[/dim]")
            _show_cost_estimates(config.models)
            return config

    c.print("\n[bold]1/4 — Agent models[/bold]\n")
    models_dict: dict[str, str] = config.models.model_dump()
    for role, label, color, desc in ROLES:
        c.print(f"[{color}]● {label}[/{color}] — {desc}")
        models_dict[role] = _pick_model(role, models_dict[role])
        c.print(f"  → [{color}]{models_dict[role]}[/{color}]\n")

    models = AgentModelConfig(**models_dict)

    c.print("[bold]2/4 — Cost estimates[/bold]\n")
    _show_cost_estimates(models)

    profile = Prompt.ask(
        "Default usage profile for alerts",
        choices=["light", "medium", "heavy"],
        default=config.usage_profile,
    )

    c.print("\n[bold]3/4 — Budgets & approvals[/bold]\n")
    budget_alert = FloatPrompt.ask(
        "Monthly LLM cost alert threshold (USD)",
        default=float(config.budget_alert_usd),
    )
    default_company_budget = FloatPrompt.ask(
        "Default company launch budget (USD)",
        default=float(config.default_company_budget_usd),
    )
    require_approval = Confirm.ask(
        "Require human approval for money & irreversible actions?",
        default=config.require_human_approval,
    )

    c.print("\n[bold]4/4 — Save[/bold]\n")
    new_config = UserConfig(
        models=models,
        budget_alert_usd=budget_alert,
        default_company_budget_usd=default_company_budget,
        require_human_approval=require_approval,
        usage_profile=profile,  # type: ignore[arg-type]
        preferred_registrars=config.preferred_registrars,
        setup_completed=True,
    )

    # Summary
    summary = Table(title="Configuration summary", border_style="green")
    summary.add_column("Key")
    summary.add_column("Value")
    for role, label, color, _ in ROLES:
        summary.add_row(label, f"[{color}]{getattr(models, role)}[/{color}]")
    summary.add_row("Usage profile", profile)
    summary.add_row("LLM alert", f"${budget_alert:.2f}/mo")
    summary.add_row("Default company budget", f"${default_company_budget:.2f}")
    summary.add_row("Human approval", "yes" if require_approval else "no")
    c.print(summary)

    est = estimate_monthly_cost(models, profile)
    c.print(
        f"\nProjected monthly LLM spend ({profile}): "
        f"[bold green]${est['total_usd']:.2f}[/bold green]\n"
    )

    if Confirm.ask("Save this configuration?", default=True):
        path = save_user_config(new_config)
        c.print(f"[green]✓ Saved to[/green] {path}")
    else:
        c.print("[yellow]Not saved.[/yellow]")
        return config

    # Credential hints
    c.print("\n[bold]API key status[/bold]")
    for role, _, color, _ in ROLES:
        mid = getattr(models, role)
        ok, key = llm_ready(mid)
        status = "[green]ready[/green]" if ok else f"[red]missing {key}[/red]"
        c.print(f"  [{color}]{role}[/{color}]: {mid} — {status}")

    c.print(
        Panel(
            "Next steps:\n"
            "  1. Copy [cyan].env.example[/cyan] → [cyan].env[/cyan] and add API keys\n"
            "  2. Launch a company:\n"
            '     [bold]autocorp launch "FocusFlow" --budget 450 '
            '--desc "AI Pomodoro + deep work tracker for freelancers"[/bold]\n'
            "  3. Monitor: [bold]autocorp status[/bold] · [bold]autocorp approve[/bold]",
            title="🚀 Ready",
            border_style="blue",
        )
    )
    return new_config
