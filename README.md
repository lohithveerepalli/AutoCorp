# AutoCorp

**Fully autonomous multi-agent AI Company Operating System.**

The human CEO only needs to say:

```text
Launch company:
Name: FocusFlow
Description: AI Pomodoro + deep work tracker for freelancers
Budget: $450
Stack preference: Next.js + Supabase + Stripe + Vercel
Tone: clean, professional
```

Then four specialized agents take over end-to-end:

| Agent | Color | Model (default) | Owns |
|-------|--------|-----------------|------|
| **Brain** | Blue | Claude Sonnet / Opus | Research, architecture, all code, GitHub, Supabase, Vercel |
| **Operator** | Green | GPT-4o | Domain research + purchase, company email, infra |
| **Marketer** | Magenta | GPT-4o | Social accounts, branding, content, growth |
| **Accountant** | Yellow | GPT-4o | Budget, approvals, Stripe, live P&L |

Agents run continuous autonomous loops, message each other over a shared SQLite brain, and only ask the human for approval on **money** and **irreversible actions**.

---

## Quick start

```bash
# Python 3.11+
git clone https://github.com/YOUR_USER/AutoCorp.git
cd AutoCorp

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env
# Add at least ANTHROPIC_API_KEY and/or OPENAI_API_KEY

# Interactive setup: models, monthly cost estimates, budget alerts
autocorp setup

# Launch a company
autocorp launch "FocusFlow" \
  --budget 450 \
  --desc "AI Pomodoro + deep work tracker for freelancers"

# Demo mode (mocks + auto-approve — no paid APIs required)
autocorp launch "FocusFlow" --budget 450 \
  --desc "AI Pomodoro + deep work tracker for freelancers" \
  --auto-approve --yes --cycles 3
```

---

## CLI

```bash
autocorp setup                 # Models, cost estimates, save config
autocorp launch "Name" -b 450 -d "..."   # One-command company launcher
autocorp run focusflow         # Continue autonomous loops
autocorp status [slug]         # Agents, budget, domain, messages
autocorp approve -p focusflow  # Money & irreversible actions
autocorp pnl focusflow         # Live P&L
autocorp messages focusflow    # Cross-agent bus
autocorp config                # Show saved configuration
```

---

## Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                     Human CEO (CLI)                         │
│         launch · approve · status · intervene               │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│              LangGraph StateGraph (continuous loops)        │
│  bootstrap → Accountant → Operator → Brain → Marketer → sync│
└───────┬──────────┬──────────┬──────────┬────────────────────┘
        │          │          │          │
   ┌────▼───┐ ┌────▼────┐ ┌───▼────┐ ┌───▼──────┐
   │Accountant│ │Operator│ │ Brain  │ │ Marketer │
   │ budget   │ │ domain │ │ code   │ │ social   │
   │ stripe   │ │ email  │ │ deploy │ │ content  │
   └────┬─────┘ └────┬───┘ └───┬────┘ └───┬──────┘
        │            │         │          │
        └────────────┴────┬────┴──────────┘
                          │
              ┌───────────▼────────────┐
              │   SQLite Shared Brain  │
              │ projects · messages ·  │
              │ budgets · domains ·    │
              │ emails · socials ·     │
              │ costs · agent_status   │
              └────────────────────────┘
```

### Tech stack

- **Python 3.11+**
- **LangGraph** + **LangChain** (`StateGraph` continuous multi-agent loops)
- **Claude** via `langchain-anthropic` (Brain)
- **GPT-4o / o1** via `langchain-openai` (other agents)
- Also: **DeepSeek**, **OpenRouter**, **Ollama** (local)
- **SQLite** shared brain
- **rich** color-coded terminals
- **PyGithub**, **httpx**, **pydantic**, **typer**, **python-dotenv**
- Real tooling hooks: Vercel CLI, Supabase API, Namecheap / Porkbun / Cloudflare, Google Workspace (optional)

---

## Mandatory features

1. **One-command launcher** — `autocorp launch "FocusFlow" --budget 450 --desc "..."`
2. **Full budget system** — live tracking, category breakdown, approval gates
3. **Domain research** — multi-registrar price comparison + purchase flow
4. **Email accounts** — `hello@`, `brain@`, `ops@`, `growth@`, `finance@`
5. **Social CMS** — X, LinkedIn, Instagram, TikTok (strong mocks + human approval)
6. **Brain owns production** — Next.js scaffold → GitHub → Supabase → Vercel
7. **Continuous autonomous loops** — agents keep working after launch (`autocorp run`)
8. **Cross-agent messaging bus** — SQLite-backed inbox / broadcast
9. **Color-coded terminals** — Brain blue · Operator green · Marketer magenta · Accountant yellow
10. **Interactive setup CLI** — choose models/APIs, estimated monthly costs (light/medium/heavy), budget alerts, save config

---

## Interactive setup (first run)

```bash
autocorp setup
```

You will:

- Pick a model per agent (Claude Sonnet/Opus, GPT-4o, o1, DeepSeek, OpenRouter, Ollama, …)
- See **real-time estimated monthly costs** for light / medium / heavy company launching
- Set default models and budget alert thresholds
- Save configuration to `data/config.json`

---

## Environment

Copy [`.env.example`](.env.example) → `.env`. Minimum for live LLM work:

```bash
ANTHROPIC_API_KEY=...   # Brain
OPENAI_API_KEY=...      # Operator / Marketer / Accountant
```

Optional integrations (all degrade gracefully to intelligent mocks):

| Variable | Purpose |
|----------|---------|
| `GITHUB_TOKEN` | Create/push repos |
| `VERCEL_TOKEN` | Production deploys |
| `SUPABASE_ACCESS_TOKEN` + `SUPABASE_ORG_ID` | DB projects |
| `PORKBUN_*` / `NAMECHEAP_*` / `CLOUDFLARE_*` | Live domain quotes |
| `STRIPE_SECRET_KEY` | Billing setup |
| Social API keys | Live posting (`AUTO_APPROVE_SOCIAL=true`) |

Without keys, AutoCorp still runs end-to-end in **mock mode** so you can demo the OS.

---

## Project layout

```text
AutoCorp/
├── autocorp/
│   ├── agents/          # Brain, Operator, Marketer, Accountant
│   ├── cli/             # Typer CLI (launch, setup, approve, …)
│   ├── core/            # Config, LLM factory, messaging, LangGraph
│   ├── db/              # SQLite shared brain
│   ├── tools/           # Domains, email, social, github, vercel, supabase, budget
│   └── ui/              # Rich consoles + setup wizard
├── data/                # DB, config, generated company apps
├── scripts/             # Demo launch script
├── tests/
├── pyproject.toml
├── .env.example
└── README.md
```

---

## Human approval model

Agents **must not** silently:

- Purchase domains
- Spend budget above auto-threshold
- Create live social accounts
- Perform other irreversible external actions

Flow:

1. Agent proposes action → `approvals` table + message to Human
2. CEO runs `autocorp approve -p <slug>`
3. `autocorp run <slug>` continues the autonomous loops

Use `--auto-approve` only for demos / CI.

---

## Development

```bash
pip install -e ".[dev]"
pytest -q
ruff check autocorp tests
```

Demo script:

```bash
chmod +x scripts/demo_launch.sh
./scripts/demo_launch.sh
```

---

## Safety & ethics

- AutoCorp is an **orchestration OS** — you are responsible for API keys, spend, and published content.
- Social and domain purchases default to **mock + approval**.
- Never commit real `.env` secrets.
- Respect platform ToS when enabling live social APIs.

---

## License

MIT — see [LICENSE](LICENSE).

---

<p align="center">
  <b>AutoCorp</b> — the human sets the vision; the company runs itself.
</p>
