"""Beautiful color-coded terminal UIs for AutoCorp agents."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from autocorp.core.models import AgentRole

THEME = Theme(
    {
        "brain": "bold blue",
        "operator": "bold green",
        "marketer": "bold magenta",
        "accountant": "bold yellow",
        "human": "bold cyan",
        "system": "bold white",
        "money": "bold green",
        "warn": "bold red",
        "muted": "dim",
    }
)

AGENT_COLORS = {
    AgentRole.BRAIN: "blue",
    AgentRole.OPERATOR: "green",
    AgentRole.MARKETER: "magenta",
    AgentRole.ACCOUNTANT: "yellow",
    AgentRole.HUMAN: "cyan",
    AgentRole.SYSTEM: "white",
}

AGENT_ICONS = {
    AgentRole.BRAIN: "🧠",
    AgentRole.OPERATOR: "⚙️",
    AgentRole.MARKETER: "📣",
    AgentRole.ACCOUNTANT: "💰",
    AgentRole.HUMAN: "👤",
    AgentRole.SYSTEM: "⚡",
}

_console: Console | None = None


def get_console() -> Console:
    global _console
    if _console is None:
        _console = Console(theme=THEME, highlight=False)
    return _console


def banner(version: str = "0.1.0") -> None:
    c = get_console()
    art = Text()
    art.append("╔══════════════════════════════════════════════════════════╗\n", style="bold cyan")
    art.append("║  ", style="bold cyan")
    art.append("A U T O C O R P", style="bold white")
    art.append("  ·  AI Company Operating System", style="dim")
    art.append("      ║\n", style="bold cyan")
    art.append("║  ", style="bold cyan")
    art.append(f"v{version}", style="muted")
    art.append("  ·  Brain · Operator · Marketer · Accountant", style="dim")
    art.append("  ║\n", style="bold cyan")
    art.append("╚══════════════════════════════════════════════════════════╝", style="bold cyan")
    c.print(art)
    c.print()


class AgentConsole:
    """Color-coded logger bound to an agent role."""

    def __init__(self, role: AgentRole) -> None:
        self.role = role
        self.console = get_console()
        self.color = AGENT_COLORS.get(role, "white")
        self.icon = AGENT_ICONS.get(role, "•")
        self.name = role.value.upper()

    def _prefix(self) -> Text:
        t = Text()
        t.append(f" {self.icon} ", style=self.color)
        t.append(f"{self.name:<11}", style=f"bold {self.color}")
        t.append("│ ", style="dim")
        return t

    def log(self, message: str) -> None:
        line = self._prefix()
        line.append_text(Text.from_markup(message))
        self.console.print(line)

    def panel(self, message: str, title: str | None = None) -> None:
        self.console.print(
            Panel(
                message,
                title=title or f"{self.icon} {self.name}",
                border_style=self.color,
                expand=False,
            )
        )

    def success(self, message: str) -> None:
        self.log(f"[green]✓[/green] {message}")

    def warn(self, message: str) -> None:
        self.log(f"[yellow]![/yellow] {message}")

    def error(self, message: str) -> None:
        self.log(f"[red]✗[/red] {message}")

    def task(self, message: str) -> None:
        self.log(f"[dim]→[/dim] {message}")


def print_budget_table(snapshot: dict[str, Any] | Any) -> None:
    c = get_console()
    if hasattr(snapshot, "model_dump"):
        snap = snapshot.model_dump()
    else:
        snap = dict(snapshot)

    table = Table(title="Budget / P&L", border_style="yellow", show_header=True)
    table.add_column("Metric", style="bold")
    table.add_column("Amount", justify="right")
    table.add_row("Budget", f"${snap.get('budget_usd', 0):,.2f}")
    table.add_row("Spent", f"[money]${snap.get('spent_usd', 0):,.2f}[/money]")
    table.add_row("Pending", f"${snap.get('pending_usd', 0):,.2f}")
    table.add_row("Remaining", f"${snap.get('remaining_usd', 0):,.2f}")
    if snap.get("by_category"):
        for cat, amt in snap["by_category"].items():
            table.add_row(f"  · {cat}", f"${amt:,.2f}")
    if snap.get("alert"):
        table.caption = f"[warn]{snap.get('alert_message', 'Budget alert')}[/warn]"
    c.print(table)


def print_domain_options(options: list[Any], limit: int = 10) -> None:
    c = get_console()
    table = Table(title="Domain Options", border_style="green")
    table.add_column("#", style="dim")
    table.add_column("Domain")
    table.add_column("Registrar")
    table.add_column("Price", justify="right")
    table.add_column("Status")
    for i, o in enumerate(options[:limit], 1):
        d = o.model_dump() if hasattr(o, "model_dump") else o
        avail = d.get("available", False)
        table.add_row(
            str(i),
            d.get("domain", ""),
            d.get("registrar", ""),
            f"${d.get('price_usd', 0):.2f}" if avail else "—",
            "[green]available[/green]" if avail else "[red]taken[/red]",
        )
    c.print(table)


def print_agent_status(statuses: list[Any]) -> None:
    c = get_console()
    table = Table(title="Agent Status", border_style="cyan")
    table.add_column("Agent")
    table.add_column("Status")
    table.add_column("Task")
    table.add_column("Loops", justify="right")
    for s in statuses:
        d = s.model_dump() if hasattr(s, "model_dump") else s
        agent = d.get("agent")
        if hasattr(agent, "value"):
            agent = agent.value
        status = d.get("status")
        if hasattr(status, "value"):
            status = status.value
        color = AGENT_COLORS.get(AgentRole(agent), "white") if agent in [a.value for a in AgentRole] else "white"
        try:
            color = AGENT_COLORS[AgentRole(agent)]
        except Exception:
            color = "white"
        table.add_row(
            f"[{color}]{str(agent).upper()}[/{color}]",
            str(status),
            (d.get("current_task") or "")[:50],
            str(d.get("loop_count", 0)),
        )
    c.print(table)


def print_messages(messages: list[Any], limit: int = 15) -> None:
    c = get_console()
    for m in messages[-limit:]:
        d = m.model_dump() if hasattr(m, "model_dump") else m
        fr = d.get("from_agent")
        if hasattr(fr, "value"):
            fr = fr.value
        to = d.get("to_agent")
        if hasattr(to, "value"):
            to = to.value
        try:
            color = AGENT_COLORS[AgentRole(fr)]
        except Exception:
            color = "white"
        c.print(
            f"[{color}]{str(fr):>10}[/{color}] → {to}: "
            f"[bold]{d.get('subject', '')}[/bold] — [dim]{(d.get('body') or '')[:80]}[/dim]"
        )
