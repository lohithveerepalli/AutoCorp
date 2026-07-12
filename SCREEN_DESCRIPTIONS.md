# AutoCorp multi-agent project OS — final layout

Primary entry: `autocorp ui` → Streamlit (`autocorp/ui/streamlit_app.py`) at http://127.0.0.1:8501.

## 1. Persistent left sidebar (all views)
- **AutoCorp logo + name** (AC mark, version)
- **+ New Project** primary button
- **Projects list** — every company from `SharedBrain.list_projects()`; click opens workspace
- **Approvals** with live pending count badge `(N)`
- **Usage & Costs**
- **Settings**
- **Dark / Light** theme toggle (persists to `data/ui_theme.json`, dark default)

## 2. No project selected
- Empty state: “Select or create a project”
- CTA to open New Project
- Auto-selects first project when any exist

## 3. Project workspace (main surface after clicking a project)
### Header
- Project **name**, **status** pill, **budget remaining**, **last activity**
- Caption: description · domain · GitHub · Vercel

### Executive team — 2×2 grid
| | |
|--|--|
| **Brain** (blue) chat | **Operator** (green) chat |
| **Marketer** (purple) chat | **Accountant** (amber) chat |

Each pane includes:
- Color accent + model id (`model_for_agent`)
- Independent scrollable history (`AgentChatService`, per project + agent)
- Role-specific quick actions → `send_user_message`
- Compose + Send with stream callback when LLM supports it
- Shared SharedBrain project context for all four

### System / Next Actions (below the grid)
- **What agents are doing** — status + task from `get_agent_statuses`
- **Needs human approval** — pending irreversible/money items
- **Recommended next steps** — CEO guidance from domain/deploy/budget/pending state
- **Pending approvals (this project)** — Approve / Reject inline

## 4. + New Project
- CEO brief form (name, description, budget slider, stack, tone, cycles, auto-approve)
- Launches via existing `launch_company` orchestration
- Selects new project and returns to workspace

## 5. Approvals (sidebar destination)
- Global pending approvals list with Approve / Reject
- Risk amounts shown

## 6. Usage & Costs
- Profile, projected monthly LLM, workspace spend
- Per-agent cost breakdown bars

## 7. Settings
- Per-agent model selectors with $/1M + API key status
- Monthly cost estimates (light/medium/heavy)
- Budget alerts + human-approval toggle · Save

## Backend
Unchanged: LangGraph agents, SharedBrain, AgentChatService, CLI launch.
