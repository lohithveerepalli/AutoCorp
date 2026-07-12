# AutoCorp Streamlit UI — Screen Descriptions

Primary entry: `autocorp ui` → Streamlit app at `autocorp/ui/streamlit_app.py` (default http://127.0.0.1:8501).

Theme: **dark by default**, toggle persists to `data/ui_theme.json`. Streamlit chrome (menu/footer/toolbar) hidden via custom CSS.

Agent colors: Brain **#3B82F6** blue · Operator **#22C55E** green · Marketer **#A855F7** purple · Accountant **#F59E0B** amber.

## Sidebar (all pages)
- AutoCorp brand mark + version
- Ordered nav: Dashboard → Launch Company → Companies → **Talk to Agents** → Approvals (badge with pending count) → Usage & Costs → Settings / Models → Help
- Active company selectbox (workspace context for chat & dashboards)
- Dark/Light theme toggle (disk-persisted)

## 1. Dashboard
- KPI cards: Active companies, Spend, Pending approvals, Est. monthly LLM
- Live agent status cards (color-coded) with task + loop count; **Chat with {Agent}** opens Talk to Agents for that role
- Recent activity feed from SharedBrain message bus
- Company list with Open action

## 2. Launch Company
- CEO brief form: name, description, budget slider, stack, tone, cycles
- Demo auto-approve checkbox
- Live LLM cost context from current model config
- Submits to `launch_company` orchestration

## 3. Companies
- Expandable list of all companies
- **Company Detail tabs:** Overview | Agents | Messages (agent-to-agent bus) | P&L | Infrastructure | Approvals
- Overview: stack, tone, GitHub, Vercel, budget progress, set active + chat, run +2 cycles
- Infrastructure: domains, emails, socials
- Approvals: per-company pending cards

## 4. Talk to Agents (primary new experience)
- Company context bar (name, status, remaining budget, domain)
- **Left:** agent selector with color, blurb, **current model** powering each agent
- **Right:** full chat for selected agent
  - User vs agent bubbles (distinct styles)
  - Model label on agent messages
  - **Quick action chips:** Review last code · Show budget · Propose next steps
  - **Clear chat** (only that company+agent thread)
  - **Export chat** (markdown download)
  - Composer with Send; streaming token display when LLM supports stream, else one-shot fallback
- History persisted in SQLite `data/agent_chats.db` keyed by project_id + agent

## 5. Approvals
- Clean cards with risk chips: money amount, irreversible, choice required
- Option radios for domain choices
- Approve / Reject wired to SharedBrain + BudgetToolkit

## 6. Usage & Costs
- Profile, projected monthly LLM, workspace spend KPIs
- Per-agent cost bars from cost estimator
- Light / medium / heavy profile comparison

## 7. Settings / Models
- Per-agent model selectors (Claude Sonnet 4.5, Opus, GPT-4o, o1, DeepSeek, OpenRouter, Ollama, …)
- Cost estimates shown next to each model (in/out per 1M) + API key ready flags
- Live monthly cost calculator for light/medium/heavy
- Budget alerts, default company budget, human-approval toggle
- Saves via `save_user_config`

## 8. Help
- Getting started steps, CLI snippets, agent color legend

## Legacy
- FastAPI HTML SPA remains at `autocorp ui --legacy-fastapi` (optional); Streamlit is the accepted CEO UI for this goal.
