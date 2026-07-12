"""LangGraph multi-agent orchestration with continuous loops."""

from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict

from autocorp.agents.accountant import AccountantAgent
from autocorp.agents.brain import BrainAgent
from autocorp.agents.marketer import MarketerAgent
from autocorp.agents.operator import OperatorAgent
from autocorp.core.config import UserConfig, get_settings, load_user_config
from autocorp.core.messaging import MessageBus
from autocorp.core.models import AgentRole, CompanyBrief, Project
from autocorp.db.brain import SharedBrain
from autocorp.ui.console import (
    banner,
    get_console,
    print_agent_status,
    print_messages,
)


class CompanyState(TypedDict, total=False):
    """Shared LangGraph state for a company run."""

    project_id: str
    brief: dict[str, Any]
    context: dict[str, Any]
    cycle: int
    max_cycles: int
    last_results: dict[str, Any]
    messages_log: Annotated[list[str], operator.add]
    halt: bool
    phase: str


def build_runtime(
    brain: SharedBrain | None = None,
    user_config: UserConfig | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    brain = brain or SharedBrain(settings.db_path)
    bus = MessageBus(brain)
    cfg = user_config or load_user_config()
    agents = {
        "brain": BrainAgent(brain, bus, cfg),
        "operator": OperatorAgent(brain, bus, cfg),
        "marketer": MarketerAgent(brain, bus, cfg),
        "accountant": AccountantAgent(brain, bus, cfg),
    }
    return {"brain_db": brain, "bus": bus, "agents": agents, "config": cfg, "settings": settings}


def create_company(brain: SharedBrain, brief: CompanyBrief) -> Project:
    project = Project(
        name=brief.name,
        description=brief.description,
        budget_usd=brief.budget_usd,
        stack=brief.stack_preference,
        tone=brief.tone,
        status="launching",
        metadata={"brief": brief.model_dump(), **brief.extra},
    )
    return brain.create_project(project)


def build_graph(runtime: dict[str, Any]):
    """Build a LangGraph StateGraph for continuous multi-agent loops."""
    from langgraph.graph import END, START, StateGraph

    agents = runtime["agents"]
    brain_db: SharedBrain = runtime["brain_db"]
    console = get_console()

    def node_bootstrap(state: CompanyState) -> dict[str, Any]:
        pid = state["project_id"]
        project = brain_db.get_project(pid)
        console.print(f"\n[bold cyan]══ Cycle {state.get('cycle', 0) + 1} ══[/bold cyan]")
        bus: MessageBus = runtime["bus"]
        if state.get("cycle", 0) == 0:
            bus.broadcast(
                pid,
                AgentRole.SYSTEM,
                "Company launched",
                f"CEO brief received for {project.name if project else pid}. Agents: go.",
                priority="high",
            )
        return {
            "cycle": state.get("cycle", 0) + 1,
            "messages_log": [f"bootstrap cycle {state.get('cycle', 0) + 1}"],
            "phase": "running",
        }

    def node_accountant(state: CompanyState) -> dict[str, Any]:
        # Accountant first so budget rails exist before spend
        res = agents["accountant"].run_once(state["project_id"], state.get("context") or {})
        return {
            "last_results": {**(state.get("last_results") or {}), "accountant": res},
            "messages_log": [f"accountant:{res.get('phase')}"],
        }

    def node_operator(state: CompanyState) -> dict[str, Any]:
        res = agents["operator"].run_once(state["project_id"], state.get("context") or {})
        return {
            "last_results": {**(state.get("last_results") or {}), "operator": res},
            "messages_log": [f"operator:{res.get('phase')}"],
        }

    def node_brain(state: CompanyState) -> dict[str, Any]:
        res = agents["brain"].run_once(state["project_id"], state.get("context") or {})
        return {
            "last_results": {**(state.get("last_results") or {}), "brain": res},
            "messages_log": [f"brain:{res.get('phase')}"],
        }

    def node_marketer(state: CompanyState) -> dict[str, Any]:
        res = agents["marketer"].run_once(state["project_id"], state.get("context") or {})
        return {
            "last_results": {**(state.get("last_results") or {}), "marketer": res},
            "messages_log": [f"marketer:{res.get('phase')}"],
        }

    def node_sync(state: CompanyState) -> dict[str, Any]:
        pid = state["project_id"]
        print_agent_status(brain_db.get_agent_statuses(pid))
        msgs = brain_db.get_thread(pid, limit=8)
        if msgs:
            console.print("[dim]Recent messages:[/dim]")
            print_messages(msgs, limit=8)
        return {"messages_log": ["sync"]}

    def should_continue(state: CompanyState) -> Literal["bootstrap", "__end__"]:
        if state.get("halt"):
            return "__end__"
        cycle = state.get("cycle", 0)
        max_cycles = state.get("max_cycles", 4)
        if cycle >= max_cycles:
            return "__end__"
        # Continuous loop: after sync, go back to bootstrap for next cycle
        return "bootstrap"

    graph = StateGraph(CompanyState)
    graph.add_node("bootstrap", node_bootstrap)
    graph.add_node("accountant", node_accountant)
    graph.add_node("operator", node_operator)
    graph.add_node("brain", node_brain)
    graph.add_node("marketer", node_marketer)
    graph.add_node("sync", node_sync)

    graph.add_edge(START, "bootstrap")
    graph.add_edge("bootstrap", "accountant")
    graph.add_edge("accountant", "operator")
    graph.add_edge("operator", "brain")
    graph.add_edge("brain", "marketer")
    graph.add_edge("marketer", "sync")
    graph.add_conditional_edges(
        "sync",
        should_continue,
        {
            "bootstrap": "bootstrap",
            "__end__": END,
        },
    )

    return graph.compile()


def launch_company(
    brief: CompanyBrief,
    max_cycles: int = 4,
    context: dict[str, Any] | None = None,
    continuous: bool = False,
) -> dict[str, Any]:
    """
    One-command company launch.

    Runs the multi-agent graph for `max_cycles` autonomous cycles.
    If continuous=True, keeps looping until interrupted (max_cycles default high).
    """
    banner()
    console = get_console()
    runtime = build_runtime()
    brain: SharedBrain = runtime["brain_db"]
    project = create_company(brain, brief)

    console.print(
        f"[bold]Launching[/bold] [cyan]{project.name}[/cyan] · "
        f"budget [yellow]${project.budget_usd:,.2f}[/yellow] · "
        f"id [dim]{project.id}[/dim]\n"
    )
    console.print(f"[dim]{project.description}[/dim]")
    console.print(f"[dim]Stack: {project.stack} · Tone: {project.tone}[/dim]\n")

    if continuous:
        max_cycles = max(max_cycles, 100)

    graph = build_graph(runtime)
    initial: CompanyState = {
        "project_id": project.id,
        "brief": brief.model_dump(),
        "context": context or {},
        "cycle": 0,
        "max_cycles": max_cycles,
        "last_results": {},
        "messages_log": [],
        "halt": False,
        "phase": "start",
    }

    try:
        final = graph.invoke(initial)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted — company state persisted.[/yellow]")
        final = initial

    project = brain.get_project(project.id)
    console.print(
        f"\n[bold green]✓ Launch cycle complete for {project.name if project else brief.name}[/bold green]"
    )
    if project:
        console.print(f"  Project ID : {project.id}")
        console.print(f"  Status     : {project.status}")
        console.print(f"  Domain     : {project.domain or 'pending approval'}")
        console.print(f"  GitHub     : {project.github_repo or '—'}")
        console.print(f"  Vercel     : {project.vercel_url or '—'}")
        console.print(f"  Spent      : ${project.spent_usd:,.2f} / ${project.budget_usd:,.2f}")
        pending = brain.list_pending_approvals(project.id)
        if pending:
            console.print(f"  [yellow]Pending approvals: {len(pending)}[/yellow]")
            console.print(f"  → Run: [cyan]autocorp approve --project {project.slug}[/cyan]")

    return {
        "project": project.model_dump(mode="json") if project else None,
        "final_state": {
            k: final.get(k)
            for k in ("project_id", "cycle", "max_cycles", "phase", "messages_log")
            if k in final
        },
        "runtime": runtime,
    }


def continue_company(
    project_id_or_slug: str,
    max_cycles: int = 2,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Continue autonomous loops for an existing company."""
    runtime = build_runtime()
    brain: SharedBrain = runtime["brain_db"]
    project = brain.get_project(project_id_or_slug) or brain.get_project_by_slug(project_id_or_slug)
    if not project:
        raise ValueError(f"Project not found: {project_id_or_slug}")

    graph = build_graph(runtime)
    state: CompanyState = {
        "project_id": project.id,
        "brief": project.metadata.get("brief") or {},
        "context": context or {},
        "cycle": 0,
        "max_cycles": max_cycles,
        "last_results": {},
        "messages_log": [],
        "halt": False,
        "phase": "continue",
    }
    final = graph.invoke(state)
    return {"project_id": project.id, "final_state": final}
