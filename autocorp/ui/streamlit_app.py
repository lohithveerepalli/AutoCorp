"""AutoCorp multi-agent project OS — Streamlit CEO dashboard.

Layout:
  Left sidebar → logo, + New Project, project list, Approvals badge,
                 Usage & Costs, Settings, theme toggle
  Main → project workspace (header + 2×2 agent chats + System / Next Actions)
       → or New Project / Approvals / Usage / Settings views
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

import streamlit as st

from streamlit_extras.add_vertical_space import add_vertical_space

from autocorp import __version__
from autocorp.core.config import (
    estimate_monthly_cost,
    get_available_models_for_role,
    get_settings,
    load_user_config,
    save_user_config,
    AgentModelConfig,
    UserConfig,
)
from autocorp.core.graph import launch_company
from autocorp.core.llm import model_ready
from autocorp.core.models import CompanyBrief
from autocorp.db.brain import SharedBrain
from autocorp.tools.budget import BudgetToolkit
from autocorp.ui.chat_service import AgentChatService
from autocorp.ui.design import (
    AGENT_BLURBS,
    AGENT_COLORS,
    AGENT_LABELS,
    AGENT_ROLES,
    agent_color,
)
from autocorp.ui.navigation import set_active_company
from autocorp.ui.theme import (
    get_theme_preference,
    set_theme_preference,
    theme_css_variables,
)
from autocorp.ui.workspace import (
    project_header_data,
    quick_actions_for_agent,
    system_next_actions_panel,
)

# Logical main views (not sticky widget keys)
VIEW_WORKSPACE = "workspace"
VIEW_NEW_PROJECT = "new_project"
VIEW_APPROVALS = "approvals"
VIEW_USAGE = "usage"
VIEW_SETTINGS = "settings"


def _css_path() -> Path:
    return Path(__file__).resolve().parent / "assets" / "streamlit_theme.css"


def inject_styles(theme: str) -> None:
    vars_map = theme_css_variables(theme)  # type: ignore[arg-type]
    var_block = "\n".join(f"  {k}: {v};" for k, v in vars_map.items())
    base = _css_path().read_text(encoding="utf-8") if _css_path().exists() else ""
    agent_vars = "\n".join(f"  --agent-{k}: {v};" for k, v in AGENT_COLORS.items())
    st.markdown(
        f"<style>\n:root {{\n{var_block}\n{agent_vars}\n}}\n{base}\n</style>",
        unsafe_allow_html=True,
    )


def brain() -> SharedBrain:
    if "brain" not in st.session_state:
        st.session_state.brain = SharedBrain(get_settings().db_path)
    return st.session_state.brain


def chat_service() -> AgentChatService:
    if "chat_service" not in st.session_state:
        st.session_state.chat_service = AgentChatService()
    return st.session_state.chat_service


def money(n: float) -> str:
    return f"${float(n or 0):,.2f}"


def toast(msg: str, icon: str = "✅") -> None:
    try:
        st.toast(msg, icon=icon)
    except Exception:
        st.success(msg)


def skeleton(lines: int = 3) -> str:
    markup = "".join('<div class="ac-skeleton"></div>' for _ in range(max(1, lines)))
    st.markdown(markup, unsafe_allow_html=True)
    return markup


def format_chat_html(text: str) -> str:
    escaped = html.escape(text or "")
    return escaped.replace("\n", "<br>\n")


def empty_state(title: str, body: str) -> None:
    st.markdown(
        f'<div class="ac-empty"><h4 style="margin:0 0 0.35rem;color:inherit">{html.escape(title)}</h4>'
        f"<p style='margin:0'>{html.escape(body)}</p></div>",
        unsafe_allow_html=True,
    )


def set_view(view: str) -> None:
    st.session_state.main_view = view


def current_view() -> str:
    return st.session_state.get("main_view") or VIEW_WORKSPACE


def resolve_project():
    slug = st.session_state.get("active_slug")
    if not slug:
        return None
    return brain().get_project_by_slug(slug) or brain().get_project(slug)


# ── Sidebar ──────────────────────────────────────────────────


def render_sidebar() -> None:
    theme = st.session_state.get("theme") or get_theme_preference()
    st.session_state.theme = theme

    with st.sidebar:
        st.markdown(
            f"""
            <div style="display:flex;gap:0.75rem;align-items:center;margin-bottom:0.85rem">
              <div style="width:38px;height:38px;border-radius:10px;
                background:linear-gradient(135deg,#0ea5e9,#10b981);
                display:flex;align-items:center;justify-content:center;
                font-weight:800;color:white;font-size:0.75rem">AC</div>
              <div>
                <div style="font-weight:700;letter-spacing:-0.02em;font-size:1.05rem">AutoCorp</div>
                <div style="font-size:0.7rem;color:var(--ac-text-muted)">AI Company OS · v{__version__}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.button("+ New Project", type="primary", use_container_width=True, key="btn_new_project"):
            set_view(VIEW_NEW_PROJECT)
            st.rerun()

        st.markdown(
            "<div style='font-size:0.68rem;text-transform:uppercase;letter-spacing:0.08em;"
            "color:var(--ac-text-muted);margin:0.85rem 0 0.4rem;font-weight:600'>Projects</div>",
            unsafe_allow_html=True,
        )

        projects = brain().list_projects()
        if not projects:
            st.caption("No projects yet.")
        else:
            for p in projects:
                active = st.session_state.get("active_slug") == p.slug and current_view() == VIEW_WORKSPACE
                label = f"{'● ' if active else ''}{p.name}"
                if st.button(
                    label,
                    key=f"proj_{p.id}",
                    use_container_width=True,
                    type="primary" if active else "secondary",
                ):
                    set_active_company(st.session_state, p.slug)
                    set_view(VIEW_WORKSPACE)
                    st.rerun()

        st.divider()

        try:
            pending_n = len(brain().list_pending_approvals())
        except Exception:
            pending_n = 0

        appr_label = f"Approvals ({pending_n})" if pending_n else "Approvals"
        if st.button(appr_label, use_container_width=True, key="btn_approvals"):
            set_view(VIEW_APPROVALS)
            st.rerun()
        if st.button("Usage & Costs", use_container_width=True, key="btn_usage"):
            set_view(VIEW_USAGE)
            st.rerun()
        if st.button("Settings", use_container_width=True, key="btn_settings"):
            set_view(VIEW_SETTINGS)
            st.rerun()

        st.divider()
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("Dark" if theme == "light" else "Light", use_container_width=True, key="btn_theme"):
                new_t = "light" if theme == "dark" else "dark"
                set_theme_preference(new_t)  # type: ignore[arg-type]
                st.session_state.theme = new_t
                st.rerun()
        with col_b:
            st.caption(f"Theme: **{theme}**")

        add_vertical_space(1)
        st.caption("4 agents · one shared company brain")


# ── Agent chat pane ──────────────────────────────────────────


def render_agent_pane(project, agent: str) -> None:
    """One of four simultaneous CEO↔agent chat windows."""
    color = agent_color(agent)
    model = chat_service().model_for_agent(agent)
    label = AGENT_LABELS[agent]

    st.markdown(
        f"""
        <div class="ac-agent-pane" style="border-color:{color};border-left:3px solid {color}">
          <div class="ac-badge" style="color:{color}"><span class="orb"></span>{label}</div>
          <div class="ac-pane-model">{html.escape(model)}</div>
          <div class="ac-pane-blurb">{html.escape(AGENT_BLURBS.get(agent, ""))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    history = chat_service().list_messages(project.id, agent, limit=40)
    with st.container(height=220):
        if not history:
            st.caption(f"No messages yet with {label}.")
        for m in history:
            if m.role == "user":
                st.markdown(
                    f"<div class='ac-chat-user'><div class='ac-chat-meta'>You</div>"
                    f"<div class='ac-chat-body'>{format_chat_html(m.content)}</div></div>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"<div class='ac-chat-agent' style='border-left-color:{color}'>"
                    f"<div class='ac-chat-meta'>{html.escape(label)} · {html.escape(m.model or model)}</div>"
                    f"<div class='ac-chat-body'>{format_chat_html(m.content)}</div></div>",
                    unsafe_allow_html=True,
                )

    # Quick actions (per agent)
    qas = quick_actions_for_agent(agent)
    if qas:
        qcols = st.columns(len(qas))
        for i, chip in enumerate(qas):
            if qcols[i].button(
                chip["label"],
                key=f"qa_{project.id}_{agent}_{chip['id']}",
                use_container_width=True,
            ):
                with st.spinner(f"{label}…"):
                    # Role-specific chips send prompt via shared chat service
                    # (same project context / AgentChatService DB)
                    chat_service().send_user_message(
                        project.id,
                        agent,
                        chip["prompt"],
                        brain=brain(),
                    )
                toast(f"{chip['label']} → {label}")
                st.rerun()

    form_key = f"form_{project.id}_{agent}_{st.session_state.get(f'nonce_{agent}', 0)}"
    with st.form(form_key, clear_on_submit=True):
        user_text = st.text_area(
            f"Message {label}",
            key=f"ta_{project.id}_{agent}",
            height=68,
            placeholder=f"Message {label}…",
            label_visibility="collapsed",
        )
        send = st.form_submit_button("Send", type="primary", use_container_width=True)

    if send and (user_text or "").strip():
        chunks: list[str] = []
        stream_slot = st.empty()

        def on_token(tok: str) -> None:
            chunks.append(tok)
            stream_slot.markdown(
                f"<div class='ac-chat-agent' style='border-left-color:{color}'>"
                f"<div class='ac-chat-meta'>{label} · streaming…</div>"
                f"<div class='ac-chat-body'>{format_chat_html(''.join(chunks))}</div></div>",
                unsafe_allow_html=True,
            )

        with st.spinner(f"{label} is thinking…"):
            chat_service().send_user_message(
                project.id,
                agent,
                user_text.strip(),
                brain=brain(),
                on_token=on_token,
            )
        st.session_state[f"nonce_{agent}"] = int(st.session_state.get(f"nonce_{agent}", 0)) + 1
        toast(f"Reply from {label}")
        st.rerun()
    elif send:
        st.warning("Type a message first.")


# ── System / Next Actions ────────────────────────────────────


def render_system_panel(project) -> None:
    panel = system_next_actions_panel(brain(), project)
    st.markdown("### System / Next Actions")
    st.caption("Shared project brain — what agents are doing and what needs you")

    st.markdown("**What agents are doing**")
    for a in panel["agent_activity"]:
        st.markdown(
            f"<div class='ac-sys-row' style='border-left:3px solid {a['color']}'>"
            f"<span class='ac-badge' style='color:{a['color']}'><span class='orb'></span>"
            f"{html.escape(a['label'])}</span> "
            f"<span style='color:var(--ac-text-muted);font-size:0.85rem'>"
            f"{html.escape(a['status'])} · {html.escape(a['task'][:100])}"
            f"</span></div>",
            unsafe_allow_html=True,
        )

    st.markdown("**Needs human approval**")
    needs = panel["needs_human_approval"]
    if not needs:
        st.caption("Nothing waiting — agents will pause here for money & irreversible acts.")
    else:
        for n in needs:
            irr = " · irreversible" if n["irreversible"] else ""
            st.markdown(
                f"- **{html.escape(n['summary'])}** ({money(n['amount_usd'])}{irr})",
                unsafe_allow_html=True,
            )

    st.markdown("**Recommended next steps**")
    for step in panel["recommended_next_steps"]:
        st.markdown(f"- {step}")

    st.markdown("**Pending approvals (this project)**")
    pending = panel["pending_approvals"]
    if not pending:
        empty_state("No pending approvals", "You're clear to keep building.")
    else:
        toolkit = BudgetToolkit(brain())
        for appr in pending:
            st.markdown(
                f"<div class='ac-card'><strong>{html.escape(appr['action'])}</strong> · "
                f"{money(appr['amount_usd'])}<br/>"
                f"<span style='color:var(--ac-text-muted)'>{html.escape(appr['description'][:160])}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
            c1, c2 = st.columns(2)
            if c1.button("Approve", key=f"ws_appr_{appr['id']}", type="primary"):
                toolkit.approve_request(appr["id"], note="Approved in workspace")
                toast("Approved")
                st.rerun()
            if c2.button("Reject", key=f"ws_rej_{appr['id']}"):
                brain().decide_approval(appr["id"], False, "Rejected in workspace")
                toast("Rejected", icon="🛑")
                st.rerun()


# ── Project workspace ────────────────────────────────────────


def render_project_workspace(project) -> None:
    header = project_header_data(brain(), project)
    last = header["last_activity"] or "—"
    if last and len(last) > 19:
        last = last[:19].replace("T", " ")

    st.markdown(
        f"""
        <div class="ac-project-header">
          <div>
            <h1 style="margin:0;letter-spacing:-0.03em;font-size:1.55rem">{html.escape(header['name'])}</h1>
            <div style="margin-top:0.35rem;color:var(--ac-text-muted);font-size:0.88rem">
              <span class="ac-status-pill">{html.escape(str(header['status']))}</span>
              · Budget remaining <strong style="color:var(--ac-accent)">{money(header['budget_remaining'])}</strong>
              · Last activity <span style="font-family:ui-monospace,monospace">{html.escape(last)}</span>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(
        f"{project.description or ''} · Domain: {project.domain or '—'} · "
        f"GitHub: {project.github_repo or '—'} · Vercel: {project.vercel_url or '—'}"
    )

    # 2×2 agent grid
    st.markdown("#### Executive team")
    r1c1, r1c2 = st.columns(2)
    with r1c1:
        render_agent_pane(project, "brain")
    with r1c2:
        render_agent_pane(project, "operator")
    r2c1, r2c2 = st.columns(2)
    with r2c1:
        render_agent_pane(project, "marketer")
    with r2c2:
        render_agent_pane(project, "accountant")

    st.divider()
    render_system_panel(project)


def render_no_project() -> None:
    empty_state(
        "Select or create a project",
        "Use + New Project in the sidebar, or click a company to open its multi-agent workspace.",
    )
    if st.button("Create your first project", type="primary"):
        set_view(VIEW_NEW_PROJECT)
        st.rerun()


# ── Other views ──────────────────────────────────────────────


def render_new_project() -> None:
    st.title("New Project")
    st.caption("CEO brief → agents take over end-to-end")
    with st.form("new_project_form"):
        name = st.text_input("Company name", value="FocusFlow")
        desc = st.text_area(
            "Description",
            value="AI Pomodoro + deep work tracker for freelancers",
        )
        budget = st.slider("Budget (USD)", 50, 5000, 450, 10)
        stack = st.text_input("Stack", value="Next.js + Supabase + Stripe + Vercel")
        tone = st.text_input("Tone", value="clean, professional")
        cycles = st.number_input("Autonomous cycles", 1, 20, 3)
        auto = st.checkbox("Demo mode: auto-approve money & socials", value=True)
        submitted = st.form_submit_button("Launch Project", type="primary", use_container_width=True)

    if submitted:
        if not name.strip():
            st.error("Name required")
            return
        skeleton(4)
        with st.spinner("Launching agents…"):
            brief = CompanyBrief(
                name=name.strip(),
                description=desc.strip(),
                budget_usd=float(budget),
                stack_preference=stack,
                tone=tone,
            )
            context = {}
            if auto:
                context = {
                    "auto_approve": True,
                    "auto_pick_domain": True,
                    "approve_domain": True,
                    "approve_social": True,
                }
            result = launch_company(brief, max_cycles=int(cycles), context=context)
            project = result.get("project") or {}
        if project.get("slug"):
            set_active_company(st.session_state, project["slug"])
            set_view(VIEW_WORKSPACE)
            toast(f"Launched {name}")
            st.rerun()
        st.success("Launch finished")


def render_approvals_view() -> None:
    st.title("Approvals")
    st.caption("Money and irreversible actions across the workspace")
    pending = brain().list_pending_approvals()
    if not pending:
        empty_state("No pending approvals", "Agents only pause here for spend & irreversible acts.")
        return
    toolkit = BudgetToolkit(brain())
    for appr in pending:
        proj = brain().get_project(appr.project_id)
        pname = proj.name if proj else appr.project_id
        st.markdown(
            f"<div class='ac-card'><div style='font-weight:700'>{html.escape(pname)} · "
            f"{html.escape(appr.action)} · {money(appr.amount_usd or 0)}</div>"
            f"<div style='color:var(--ac-text-muted)'>{html.escape(appr.description or '')}</div></div>",
            unsafe_allow_html=True,
        )
        c1, c2 = st.columns(2)
        if c1.button("Approve", key=f"g_appr_{appr.id}", type="primary"):
            toolkit.approve_request(appr.id, note="Approved globally")
            toast("Approved")
            st.rerun()
        if c2.button("Reject", key=f"g_rej_{appr.id}"):
            brain().decide_approval(appr.id, False, "Rejected")
            toast("Rejected", icon="🛑")
            st.rerun()


def render_usage_view() -> None:
    st.title("Usage & Costs")
    cfg = load_user_config()
    est = estimate_monthly_cost(cfg.models, cfg.usage_profile)
    projects = brain().list_projects()
    spent = sum(p.spent_usd for p in projects)
    c1, c2, c3 = st.columns(3)
    c1.metric("Profile", cfg.usage_profile)
    c2.metric("Projected LLM / mo", money(est["total_usd"]))
    c3.metric("Workspace spend", money(spent))
    st.subheader("By agent")
    for role, val in (est.get("breakdown") or {}).items():
        st.write(f"**{AGENT_LABELS.get(role, role)}** · {money(val)}")
        st.progress(min(1.0, float(val) / max(est["total_usd"], 0.01)))


def render_settings_view() -> None:
    st.title("Settings")
    st.caption("Models, costs, budget alerts")
    cfg = load_user_config()
    models_data = dict(cfg.models.model_dump())
    for role in AGENT_ROLES:
        st.markdown(
            f"<div class='ac-badge' style='color:{agent_color(role)}'>"
            f"<span class='orb'></span>{AGENT_LABELS[role]}</div>",
            unsafe_allow_html=True,
        )
        options = get_available_models_for_role(role)  # type: ignore[arg-type]
        ids = [mid for mid, _ in options]
        labels = []
        for mid, meta in options:
            ready, key = model_ready(mid)
            flag = "✓ key" if ready else f"✗ {key}"
            labels.append(
                f"{meta.get('label', mid)} · ${meta.get('input_per_m', 0)}/"
                f"${meta.get('output_per_m', 0)} per 1M · {flag}"
            )
        current = models_data.get(role, ids[0] if ids else "")
        idx = ids.index(current) if current in ids else 0
        pick = st.selectbox(
            f"Model · {role}",
            range(len(ids)),
            format_func=lambda i, labels=labels: labels[i],
            index=idx,
            key=f"set_model_{role}",
        )
        models_data[role] = ids[pick]

    models = AgentModelConfig(**models_data)
    st.subheader("Monthly cost estimate")
    for profile in ("light", "medium", "heavy"):
        e = estimate_monthly_cost(models, profile)
        st.write(f"**{e['profile_label']}** · {money(e['total_usd'])}")

    profile = st.selectbox(
        "Usage profile",
        ["light", "medium", "heavy"],
        index=["light", "medium", "heavy"].index(cfg.usage_profile),
    )
    alert = st.number_input("LLM alert USD", value=float(cfg.budget_alert_usd), min_value=0.0)
    company_budget = st.number_input(
        "Default company budget",
        value=float(cfg.default_company_budget_usd),
        min_value=1.0,
    )
    require = st.checkbox("Require human approval", value=cfg.require_human_approval)
    if st.button("Save", type="primary"):
        save_user_config(
            UserConfig(
                models=models,
                budget_alert_usd=float(alert),
                default_company_budget_usd=float(company_budget),
                require_human_approval=require,
                usage_profile=profile,  # type: ignore[arg-type]
                preferred_registrars=cfg.preferred_registrars,
                setup_completed=True,
            )
        )
        toast("Settings saved")


# ── Main ─────────────────────────────────────────────────────


def main() -> None:
    st.set_page_config(
        page_title="AutoCorp — AI Company OS",
        page_icon="◈",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    if "theme" not in st.session_state:
        st.session_state.theme = get_theme_preference()
    if "main_view" not in st.session_state:
        st.session_state.main_view = VIEW_WORKSPACE

    inject_styles(st.session_state.theme)
    render_sidebar()

    view = current_view()
    if view == VIEW_NEW_PROJECT:
        render_new_project()
    elif view == VIEW_APPROVALS:
        render_approvals_view()
    elif view == VIEW_USAGE:
        render_usage_view()
    elif view == VIEW_SETTINGS:
        render_settings_view()
    else:
        project = resolve_project()
        if project is None:
            # Auto-select first project if any
            projects = brain().list_projects()
            if projects:
                set_active_company(st.session_state, projects[0].slug)
                project = projects[0]
        if project is None:
            render_no_project()
        else:
            if not st.session_state.get("_ws_skel"):
                skeleton(3)
                st.session_state._ws_skel = True
            render_project_workspace(project)


if __name__ == "__main__":
    main()
