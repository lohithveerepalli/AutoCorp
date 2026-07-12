"""AutoCorp premium Streamlit CEO dashboard with Talk to Agents."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

import streamlit as st

# streamlit-extras (required dependency — used for premium spacing/cards)
from streamlit_extras.add_vertical_space import add_vertical_space
from streamlit_extras.colored_header import colored_header
from streamlit_extras.metric_cards import style_metric_cards

from autocorp import __version__
from autocorp.core.config import (
    MODEL_CATALOG,
    estimate_monthly_cost,
    get_available_models_for_role,
    get_settings,
    load_user_config,
    save_user_config,
    AgentModelConfig,
    UserConfig,
)
from autocorp.core.graph import continue_company, launch_company
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
    NAV_PAGES,
    QUICK_ACTION_CHIPS,
    agent_color,
    nav_pages,
)
from autocorp.ui.navigation import (
    apply_nav_destination,
    build_nav_options,
    read_company_selection,
    read_nav_selection,
    set_active_company,
    sync_company_select_from_active_slug,
    sync_radio_from_nav_page,
)
from autocorp.ui.theme import (
    get_theme_preference,
    set_theme_preference,
    theme_css_variables,
)

# ── bootstrap ────────────────────────────────────────────────


def _css_path() -> Path:
    return Path(__file__).resolve().parent / "assets" / "streamlit_theme.css"


def inject_styles(theme: str) -> None:
    vars_map = theme_css_variables(theme)  # type: ignore[arg-type]
    var_block = "\n".join(f"  {k}: {v};" for k, v in vars_map.items())
    base = ""
    p = _css_path()
    if p.exists():
        base = p.read_text(encoding="utf-8")
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
    """Render loading skeleton rows; returns HTML (also injected into the page)."""
    markup = "".join('<div class="ac-skeleton"></div>' for _ in range(max(1, lines)))
    st.markdown(markup, unsafe_allow_html=True)
    return markup


def empty_state(title: str, body: str) -> None:
    st.markdown(
        f'<div class="ac-empty"><h4 style="margin:0 0 0.35rem;color:inherit">{html.escape(title)}</h4>'
        f"<p style='margin:0'>{html.escape(body)}</p></div>",
        unsafe_allow_html=True,
    )


def go_to_page(
    page: str,
    *,
    agent: str | None = None,
    company_slug: str | None = None,
) -> None:
    """Deep-link helper: sync nav_page + sticky nav_radio, then rerun."""
    try:
        pending_n = len(brain().list_pending_approvals())
    except Exception:
        pending_n = 0
    apply_nav_destination(
        st.session_state,
        page,
        agent=agent,
        pending_approvals=pending_n,
        company_slug=company_slug,
    )
    st.rerun()


def kpi_html(label: str, value: str) -> str:
    return (
        f'<div class="ac-kpi"><div class="label">{html.escape(label)}</div>'
        f'<div class="value">{html.escape(value)}</div></div>'
    )


# ── page helpers ─────────────────────────────────────────────


def render_sidebar() -> str:
    theme = st.session_state.get("theme") or get_theme_preference()
    st.session_state.theme = theme

    with st.sidebar:
        st.markdown(
            f"""
            <div style="display:flex;gap:0.75rem;align-items:center;margin-bottom:1rem">
              <div style="width:36px;height:36px;border-radius:10px;background:linear-gradient(135deg,#0ea5e9,#10b981);
                          display:flex;align-items:center;justify-content:center;font-weight:800;color:white;font-size:0.75rem">AC</div>
              <div>
                <div style="font-weight:700;letter-spacing:-0.02em">AutoCorp</div>
                <div style="font-size:0.72rem;color:var(--ac-text-muted)">AI Company OS · v{__version__}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        try:
            pending_n = len(brain().list_pending_approvals())
        except Exception:
            pending_n = 0

        options = build_nav_options(pending_n)
        # Critical: sync sticky radio key BEFORE widget create (deep links)
        sync_radio_from_nav_page(st.session_state, pending_n)

        choice = st.radio(
            "Navigation",
            options,
            label_visibility="collapsed",
            key="nav_radio",
        )
        page = read_nav_selection(choice, st.session_state)

        st.divider()
        companies = brain().list_projects()
        slugs = [c.slug for c in companies]
        if slugs:
            # Critical: sync sticky company_select BEFORE selectbox (deep links)
            sync_company_select_from_active_slug(st.session_state, slugs)
            sel = st.selectbox(
                "Active company",
                slugs,
                key="company_select",
            )
            read_company_selection(sel, st.session_state)
        else:
            st.caption("No companies yet — launch one.")
            st.session_state.active_slug = None
            st.session_state.pop("company_select", None)

        st.divider()
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("Dark" if theme == "light" else "Light", use_container_width=True):
                new_t = "light" if theme == "dark" else "dark"
                set_theme_preference(new_t)  # type: ignore[arg-type]
                st.session_state.theme = new_t
                st.rerun()
        with col_b:
            st.caption(f"Theme: **{theme}**")

        st.caption("Talk to Agents = CEO direct line")
        add_vertical_space(1)
    return page


def resolve_project():
    slug = st.session_state.get("active_slug")
    if not slug:
        return None
    return brain().get_project_by_slug(slug) or brain().get_project(slug)


# ── screens ──────────────────────────────────────────────────


def page_dashboard() -> None:
    colored_header(
        label="Dashboard",
        description="Command center for your autonomous company fleet",
        color_name="green-70",
    )

    # Brief skeleton while first paint loads data (visible loading affordance)
    if st.session_state.pop("_show_dash_skeleton", False):
        skeleton(4)

    projects = brain().list_projects()
    pending = brain().list_pending_approvals()
    spent = sum(p.spent_usd for p in projects)
    cfg = load_user_config()
    try:
        est = estimate_monthly_cost(cfg.models, cfg.usage_profile)
        llm_cost = money(est["total_usd"])
    except Exception:
        llm_cost = "—"

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Active companies", str(len(projects)))
    c2.metric("Spend", money(spent))
    c3.metric("Pending approvals", str(len(pending)))
    c4.metric("Est. monthly LLM", llm_cost)
    style_metric_cards(
        background_color="rgba(15,23,42,0.55)",
        border_left_color="#10B981",
        border_color="rgba(148,163,184,0.12)",
        box_shadow="0 8px 24px rgba(0,0,0,0.25)",
    )

    st.subheader("Agent status")
    st.caption("Click an agent to open Talk to Agents")
    project = resolve_project()
    statuses = {s.agent.value: s for s in (brain().get_agent_statuses(project.id) if project else [])}

    cols = st.columns(4)
    for i, role in enumerate(AGENT_ROLES):
        with cols[i]:
            color = agent_color(role)
            st_obj = statuses.get(role)
            task = (st_obj.current_task if st_obj else "") or "Waiting for launch"
            status = (st_obj.status.value if st_obj and hasattr(st_obj.status, "value") else (st_obj.status if st_obj else "idle"))
            loops = st_obj.loop_count if st_obj else 0
            st.markdown(
                f"""
                <div class="ac-agent-card" style="--agent-color:{color};border-left-color:{color}">
                  <div class="ac-badge" style="color:{color}"><span class="orb"></span>{AGENT_LABELS[role]}</div>
                  <div style="margin-top:0.5rem;font-size:0.88rem;color:var(--ac-text-muted)">{html.escape(str(task))}</div>
                  <div style="margin-top:0.45rem;font-size:0.72rem;color:var(--ac-text-muted)">{html.escape(str(status))} · loops {loops}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button(f"Chat with {AGENT_LABELS[role]}", key=f"dash_chat_{role}", use_container_width=True):
                go_to_page("Talk to Agents", agent=role)

    st.subheader("Recent activity")
    if not project:
        empty_state("No company selected", "Launch a company or pick one in the sidebar.")
    else:
        msgs = brain().get_thread(project.id, limit=12)
        if not msgs:
            empty_state("No activity yet", "Agents will post here once the company is running.")
        else:
            for m in reversed(msgs[-12:]):
                fr = m.from_agent.value if hasattr(m.from_agent, "value") else m.from_agent
                color = agent_color(str(fr)) if str(fr) in AGENT_COLORS else "#67E8F9"
                st.markdown(
                    f"""
                    <div class="ac-card">
                      <div class="ac-badge" style="color:{color}"><span class="orb"></span>{html.escape(str(fr))}</div>
                      <div style="font-weight:600;margin-top:0.35rem">{html.escape(m.subject)}</div>
                      <div style="color:var(--ac-text-muted);font-size:0.86rem;margin-top:0.2rem">{html.escape((m.body or "")[:220])}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    st.subheader("Companies")
    if not projects:
        empty_state("No companies", "Use Launch Company to start FocusFlow or any new venture.")
    else:
        for p in projects:
            cols = st.columns([4, 1])
            cols[0].markdown(
                f"**{p.name}** · `{p.status}` · {money(p.spent_usd)}/{money(p.budget_usd)} · {p.domain or 'no domain'}"
            )
            if cols[1].button("Open", key=f"open_{p.id}"):
                go_to_page("Companies", company_slug=p.slug)


def page_launch() -> None:
    st.title("Launch Company")
    st.caption("One CEO brief. Four agents take over end-to-end.")

    with st.form("launch_form"):
        name = st.text_input("Company name", value="FocusFlow")
        desc = st.text_area(
            "Description",
            value="AI Pomodoro + deep work tracker for freelancers",
        )
        budget = st.slider("Budget (USD)", min_value=50, max_value=5000, value=450, step=10)
        stack = st.text_input("Preferred stack", value="Next.js + Supabase + Stripe + Vercel")
        tone = st.text_input("Tone", value="clean, professional")
        cycles = st.number_input("Autonomous cycles", min_value=1, max_value=20, value=3)
        auto = st.checkbox("Demo mode: auto-approve money & socials", value=True)
        submitted = st.form_submit_button("Launch Company", type="primary", use_container_width=True)

    cfg = load_user_config()
    est = estimate_monthly_cost(cfg.models, cfg.usage_profile)
    st.info(
        f"Live LLM context ({cfg.usage_profile}): **{money(est['total_usd'])}/mo** estimated — "
        "company budget is separate infra/domain spend."
    )

    if submitted:
        if not name.strip():
            st.error("Company name required")
            return
        skeleton_slot = st.empty()
        with skeleton_slot.container():
            st.caption("Provisioning agents…")
            skeleton(5)
        with st.spinner("Launching autonomous agents…"):
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
        skeleton_slot.empty()
        toast(f"Launched {name}")
        if project.get("slug"):
            set_active_company(st.session_state, project["slug"])
        st.success(
            f"Live · domain {project.get('domain') or 'pending'} · "
            f"{project.get('vercel_url') or '—'}"
        )


def page_companies() -> None:
    st.title("Companies")
    projects = brain().list_projects()
    if not projects:
        empty_state("No companies yet", "Launch your first company from the sidebar.")
        return

    for p in projects:
        with st.expander(f"{p.name} · {p.status}", expanded=st.session_state.get("company_detail") == p.slug):
            st.write(p.description)
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Budget left", money(p.budget_usd - p.spent_usd))
            c2.metric("Spent", money(p.spent_usd))
            c3.metric("Domain", p.domain or "—")
            c4.metric("Status", p.status)

            tabs = st.tabs(
                ["Overview", "Agents", "Messages", "P&L", "Infrastructure", "Approvals"]
            )
            with tabs[0]:
                st.markdown(f"**Stack:** {p.stack}")
                st.markdown(f"**Tone:** {p.tone}")
                st.markdown(f"**GitHub:** `{p.github_repo or '—'}`")
                st.markdown(f"**Vercel:** {p.vercel_url or '—'}")
                pct = (p.spent_usd / p.budget_usd * 100) if p.budget_usd else 0
                st.progress(min(1.0, pct / 100.0), text=f"Budget utilization {pct:.1f}%")
                if st.button("Set active + chat", key=f"act_{p.id}"):
                    go_to_page("Talk to Agents", company_slug=p.slug)
                if st.button("Run +2 cycles", key=f"run_{p.id}"):
                    sk = st.empty()
                    with sk.container():
                        skeleton(3)
                    with st.spinner("Running…"):
                        continue_company(
                            p.slug,
                            max_cycles=2,
                            context={
                                "auto_approve": True,
                                "approve_domain": True,
                                "approve_social": True,
                            },
                        )
                    sk.empty()
                    toast("Cycles complete")
                    st.rerun()

            with tabs[1]:
                for s in brain().get_agent_statuses(p.id):
                    role = s.agent.value
                    color = agent_color(role)
                    st.markdown(
                        f"<div class='ac-agent-card' style='border-left-color:{color}'>"
                        f"<span class='ac-badge' style='color:{color}'><span class='orb'></span>{role}</span> "
                        f"— {html.escape(s.current_task or s.status.value)} · loops {s.loop_count}</div>",
                        unsafe_allow_html=True,
                    )

            with tabs[2]:
                for m in brain().get_thread(p.id, limit=30):
                    fr = m.from_agent.value if hasattr(m.from_agent, "value") else m.from_agent
                    st.markdown(f"**{fr} → {m.to_agent}** · {m.subject}")
                    st.caption((m.body or "")[:300])

            with tabs[3]:
                snap = brain().budget_snapshot(p.id)
                st.metric("Remaining", money(snap.remaining_usd))
                st.json(snap.by_category)
                for c in brain().list_costs(p.id):
                    flag = "✓" if c.approved else "…"
                    st.write(f"{flag} {money(c.amount_usd)} · {c.category.value} · {c.description}")

            with tabs[4]:
                st.subheader("Domains")
                for d in brain().list_domain_options(p.id)[:12]:
                    st.write(
                        f"{d.domain} · {d.registrar} · "
                        f"{money(d.price_usd) if d.available else 'taken'}"
                    )
                st.subheader("Emails")
                for e in brain().list_emails(p.id):
                    st.write(f"{e.address} ({e.role})")
                st.subheader("Socials")
                for s in brain().list_socials(p.id):
                    st.write(f"{s.platform}: {s.handle} [{s.status}]")

            with tabs[5]:
                render_approvals_list(project_id=p.id)


def page_talk_to_agents() -> None:
    st.title("Talk to Agents")
    st.caption("Direct line to your executive team — like chatting with real leaders")

    project = resolve_project()
    if not project:
        empty_state(
            "Select a company first",
            "Pick an active company in the sidebar, or launch one.",
        )
        return

    st.markdown(
        f"**Company context:** {project.name} · `{project.status}` · "
        f"budget {money(project.budget_usd - project.spent_usd)} left · "
        f"{project.domain or 'no domain'}"
    )

    left, right = st.columns([1, 2.4])

    with left:
        st.subheader("Team")
        if "chat_agent" not in st.session_state:
            st.session_state.chat_agent = "brain"
        for role in AGENT_ROLES:
            color = agent_color(role)
            model = chat_service().model_for_agent(role)
            active = st.session_state.chat_agent == role
            border = f"2px solid {color}" if active else "1px solid var(--ac-border)"
            st.markdown(
                f"""
                <div class="ac-agent-card" style="border:{border};border-left:3px solid {color}">
                  <div class="ac-badge" style="color:{color}"><span class="orb"></span>{AGENT_LABELS[role]}</div>
                  <div style="font-size:0.78rem;color:var(--ac-text-muted);margin-top:0.35rem">{AGENT_BLURBS[role]}</div>
                  <div style="font-size:0.72rem;margin-top:0.4rem;font-family:ui-monospace,monospace">{html.escape(model)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button(
                "Select" if not active else "Selected",
                key=f"sel_{role}",
                disabled=active,
                use_container_width=True,
            ):
                st.session_state.chat_agent = role
                st.rerun()

    agent = st.session_state.chat_agent
    color = agent_color(agent)
    model = chat_service().model_for_agent(agent)

    with right:
        head_l, head_r = st.columns([3, 2])
        with head_l:
            st.markdown(
                f"<div class='ac-badge' style='color:{color}'><span class='orb'></span>"
                f"Chat with {AGENT_LABELS[agent]}</div>",
                unsafe_allow_html=True,
            )
            st.caption(f"Powered by **{model}**")
        with head_r:
            b1, b2 = st.columns(2)
            if b1.button("Clear chat", use_container_width=True):
                n = chat_service().clear_thread(project.id, agent)
                toast(f"Cleared {n} messages", icon="🧹")
                st.rerun()
            export_md = chat_service().export_thread(project.id, agent, fmt="markdown")
            b2.download_button(
                "Export chat",
                data=export_md,
                file_name=f"{project.slug}_{agent}_chat.md",
                mime="text/markdown",
                use_container_width=True,
            )

        # Quick action chips
        st.write("Quick actions")
        chip_cols = st.columns(len(QUICK_ACTION_CHIPS))
        for i, chip in enumerate(QUICK_ACTION_CHIPS):
            if chip_cols[i].button(chip["label"], key=f"chip_{agent}_{chip['id']}"):
                st.session_state.pending_chat_send = chip["prompt"]
                st.rerun()

        # Message history bubbles
        history = chat_service().list_messages(project.id, agent)
        chat_box = st.container()
        with chat_box:
            if not history:
                empty_state(
                    f"Start a conversation with {AGENT_LABELS[agent]}",
                    "Ask about strategy, budget, code, domains, or growth.",
                )
            for m in history:
                if m.role == "user":
                    st.markdown(
                        f"<div class='ac-chat-user'><div class='ac-chat-meta'>You · CEO</div>"
                        f"{html.escape(m.content)}</div>",
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        f"<div class='ac-chat-agent' style='--agent-color:{color};border-left-color:{color}'>"
                        f"<div class='ac-chat-meta'>{html.escape(AGENT_LABELS[agent])} · "
                        f"{html.escape(m.model or model)}</div>"
                        f"{html.escape(m.content)}</div>",
                        unsafe_allow_html=True,
                    )

        # Composer
        pending = st.session_state.pop("pending_chat_send", None)
        default_val = pending or ""
        with st.form(f"chat_form_{agent}", clear_on_submit=True):
            user_text = st.text_area(
                "Message",
                value=default_val,
                placeholder=f"Message {AGENT_LABELS[agent]}…",
                height=100,
                label_visibility="collapsed",
            )
            send = st.form_submit_button("Send", type="primary", use_container_width=True)

        if send and user_text.strip():
            stream_area = st.empty()
            sk = st.empty()
            with sk.container():
                skeleton(2)
            chunks: list[str] = []

            def on_token(tok: str) -> None:
                chunks.append(tok)
                sk.empty()
                stream_area.markdown(
                    f"<div class='ac-chat-agent' style='border-left-color:{color}'>"
                    f"<div class='ac-chat-meta'>{AGENT_LABELS[agent]} · streaming…</div>"
                    f"{html.escape(''.join(chunks))}</div>",
                    unsafe_allow_html=True,
                )

            with st.spinner(f"{AGENT_LABELS[agent]} is thinking…"):
                chat_service().send_user_message(
                    project.id,
                    agent,
                    user_text.strip(),
                    brain=brain(),
                    on_token=on_token,
                )
            sk.empty()
            toast(f"Reply from {AGENT_LABELS[agent]}")
            st.rerun()
        elif send:
            st.warning("Type a message first.")


def render_approvals_list(project_id: str | None = None) -> None:
    pending = brain().list_pending_approvals(project_id)
    if not pending:
        empty_state("No pending approvals", "Agents only pause for money and irreversible actions.")
        return
    toolkit = BudgetToolkit(brain())
    for appr in pending:
        amount = appr.amount_usd or 0
        risks = []
        if amount > 0:
            risks.append(f'<span class="ac-risk ac-risk-money">{money(amount)}</span>')
        if appr.irreversible:
            risks.append('<span class="ac-risk ac-risk-irreversible">Irreversible</span>')
        if appr.action == "choose_option":
            risks.append('<span class="ac-risk ac-risk-choice">Choice</span>')
        st.markdown(
            f"""
            <div class="ac-card">
              <div style="font-weight:700">{html.escape(appr.action)} · {money(amount)}</div>
              <div style="color:var(--ac-text-muted);margin:0.35rem 0">{html.escape(appr.description or "")}</div>
              <div>{''.join(risks) or '<span class="ac-risk">Review</span>'}</div>
              <div style="font-size:0.72rem;color:var(--ac-text-muted);margin-top:0.4rem;font-family:ui-monospace,monospace">{html.escape(appr.id)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        option_idx = 0
        if appr.options:
            labels = [
                o.get("label") or o.get("domain") or str(o) for o in appr.options
            ]
            option_idx = st.radio(
                "Options",
                range(len(labels)),
                format_func=lambda i, labels=labels: labels[i],
                key=f"opt_{appr.id}",
                horizontal=True,
            )
        c1, c2 = st.columns(2)
        if c1.button("Approve", key=f"appr_{appr.id}", type="primary"):
            if appr.action == "choose_option" and appr.options:
                pick = appr.options[int(option_idx)]
                p = brain().get_project(appr.project_id)
                if p:
                    p.metadata["selected_domain"] = pick
                    p.metadata["preferred_domain"] = pick
                    brain().update_project(p)
                brain().decide_approval(appr.id, True, f"Chose option {option_idx}")
            else:
                toolkit.approve_request(appr.id, note="Approved via Streamlit UI")
            toast("Approved")
            st.rerun()
        if c2.button("Reject", key=f"rej_{appr.id}"):
            brain().decide_approval(appr.id, False, "Rejected via Streamlit UI")
            toast("Rejected", icon="🛑")
            st.rerun()


def page_approvals() -> None:
    st.title("Approvals")
    st.caption("Money and irreversible actions requiring the human CEO")
    render_approvals_list()


def page_usage() -> None:
    st.title("Usage & Costs")
    cfg = load_user_config()
    est_all = {
        p: estimate_monthly_cost(cfg.models, p) for p in ("light", "medium", "heavy")
    }
    active = est_all[cfg.usage_profile]
    c1, c2, c3 = st.columns(3)
    c1.metric("Profile", cfg.usage_profile)
    c2.metric("Projected LLM / mo", money(active["total_usd"]))
    projects = brain().list_projects()
    c3.metric("Workspace spend", money(sum(p.spent_usd for p in projects)))

    st.subheader("LLM cost by agent")
    breakdown = active.get("breakdown") or {}
    for role in AGENT_ROLES:
        val = float(breakdown.get(role, 0))
        st.markdown(
            f"**{AGENT_LABELS[role]}** · {money(val)}",
        )
        st.progress(min(1.0, val / max(active["total_usd"], 0.01)))

    st.subheader("Profile comparison")
    for p, data in est_all.items():
        st.write(
            f"{'→ ' if p == cfg.usage_profile else ''}"
            f"**{data['profile_label']}** · {data['companies_per_month']} cos · {money(data['total_usd'])}"
        )


def page_settings() -> None:
    st.title("Settings / Models")
    st.caption("Choose models, review costs, set budget alerts")
    cfg = load_user_config()

    models_data: dict[str, str] = dict(cfg.models.model_dump())
    for role in AGENT_ROLES:
        st.markdown(
            f"<div class='ac-badge' style='color:{agent_color(role)}'>"
            f"<span class='orb'></span>{AGENT_LABELS[role]}</div>",
            unsafe_allow_html=True,
        )
        options = get_available_models_for_role(role)  # type: ignore[arg-type]
        labels = []
        ids = []
        for mid, meta in options:
            ready, key = model_ready(mid)
            flag = "✓ key" if ready else f"✗ {key}"
            labels.append(
                f"{meta.get('label', mid)} · ${meta.get('input_per_m', 0)}/"
                f"${meta.get('output_per_m', 0)} per 1M · {flag}"
            )
            ids.append(mid)
        current = models_data.get(role, ids[0] if ids else "")
        idx = ids.index(current) if current in ids else 0
        pick = st.selectbox(
            f"Model for {role}",
            range(len(ids)),
            format_func=lambda i, labels=labels: labels[i],
            index=idx,
            key=f"model_{role}",
        )
        models_data[role] = ids[pick]
        st.caption(AGENT_BLURBS[role])

    st.subheader("Live monthly cost calculator")
    models = AgentModelConfig(**models_data)
    for profile in ("light", "medium", "heavy"):
        e = estimate_monthly_cost(models, profile)
        b = e["breakdown"]
        st.write(
            f"**{e['profile_label']}** · total {money(e['total_usd'])} · "
            f"Brain {money(b['brain'])} · Ops {money(b['operator'])} · "
            f"Mkt {money(b['marketer'])} · Acct {money(b['accountant'])}"
        )

    st.subheader("Budget alerts")
    profile = st.selectbox(
        "Default usage profile",
        ["light", "medium", "heavy"],
        index=["light", "medium", "heavy"].index(cfg.usage_profile),
    )
    alert = st.number_input("Monthly LLM alert (USD)", value=float(cfg.budget_alert_usd), min_value=0.0)
    company_budget = st.number_input(
        "Default company budget (USD)",
        value=float(cfg.default_company_budget_usd),
        min_value=1.0,
    )
    require = st.checkbox(
        "Require human approval for money & irreversible actions",
        value=cfg.require_human_approval,
    )

    if st.button("Save configuration", type="primary"):
        new_cfg = UserConfig(
            models=models,
            budget_alert_usd=float(alert),
            default_company_budget_usd=float(company_budget),
            require_human_approval=require,
            usage_profile=profile,  # type: ignore[arg-type]
            preferred_registrars=cfg.preferred_registrars,
            setup_completed=True,
        )
        path = save_user_config(new_cfg)
        toast(f"Saved to {path}")
        st.success("Configuration saved")


def page_help() -> None:
    st.title("Help")
    st.markdown(
        """
### Getting started
1. **Settings / Models** — pick Claude / GPT / DeepSeek / Ollama per agent  
2. **Launch Company** — CEO brief + budget  
3. **Talk to Agents** — chat with Brain, Operator, Marketer, Accountant  
4. **Approvals** — money & irreversible actions  

### CLI
```bash
autocorp ui          # this Streamlit dashboard
autocorp launch "FocusFlow" --budget 450 --auto-approve --yes
```

### Agent colors
- **Brain** blue · **Operator** green · **Marketer** purple · **Accountant** amber
"""
    )


# ── main ─────────────────────────────────────────────────────


def main() -> None:
    st.set_page_config(
        page_title="AutoCorp — AI Company OS",
        page_icon="◈",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    if "theme" not in st.session_state:
        st.session_state.theme = get_theme_preference()
    inject_styles(st.session_state.theme)

    page = render_sidebar()

    routes = {
        "Dashboard": page_dashboard,
        "Launch Company": page_launch,
        "Companies": page_companies,
        "Talk to Agents": page_talk_to_agents,
        "Approvals": page_approvals,
        "Usage & Costs": page_usage,
        "Settings / Models": page_settings,
        "Help": page_help,
    }
    # Ensure NAV_PAGES stay in sync
    assert set(routes) == set(NAV_PAGES)
    routes.get(page, page_dashboard)()


if __name__ == "__main__":
    main()
