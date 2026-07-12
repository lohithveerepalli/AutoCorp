"""SQLite shared brain — projects, messages, budgets, domains, emails, socials, costs."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from autocorp.core.models import (
    AgentRole,
    AgentStateRecord,
    AgentStatus,
    ApprovalRequest,
    ApprovalStatus,
    BudgetSnapshot,
    CostCategory,
    CostEntry,
    DomainOption,
    EmailAccount,
    Message,
    Project,
    SocialAccount,
    SocialPost,
    utcnow,
)


def _ser(obj: Any) -> str:
    if obj is None:
        return ""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "model_dump"):
        return json.dumps(obj.model_dump(mode="json"))
    if isinstance(obj, (dict, list)):
        return json.dumps(obj)
    if isinstance(obj, Enum_like := type(obj)) and hasattr(obj, "value"):
        return str(obj.value)
    return str(obj)


def _json(val: str | None, default: Any = None) -> Any:
    if not val:
        return default if default is not None else {}
    try:
        return json.loads(val)
    except json.JSONDecodeError:
        return default if default is not None else {}


SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT NOT NULL,
    description TEXT,
    budget_usd REAL NOT NULL,
    spent_usd REAL DEFAULT 0,
    stack TEXT,
    tone TEXT,
    status TEXT DEFAULT 'launching',
    github_repo TEXT,
    vercel_url TEXT,
    supabase_project_id TEXT,
    domain TEXT,
    created_at TEXT,
    updated_at TEXT,
    metadata TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    from_agent TEXT NOT NULL,
    to_agent TEXT NOT NULL,
    subject TEXT,
    body TEXT,
    priority TEXT DEFAULT 'normal',
    requires_reply INTEGER DEFAULT 0,
    parent_id TEXT,
    payload TEXT,
    read INTEGER DEFAULT 0,
    created_at TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS costs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    category TEXT NOT NULL,
    amount_usd REAL NOT NULL,
    description TEXT,
    vendor TEXT,
    approved INTEGER DEFAULT 0,
    approved_by TEXT,
    recurring_monthly INTEGER DEFAULT 0,
    metadata TEXT,
    created_at TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    action TEXT NOT NULL,
    description TEXT,
    amount_usd REAL DEFAULT 0,
    irreversible INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending',
    options TEXT,
    metadata TEXT,
    decided_at TEXT,
    decision_note TEXT,
    created_at TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS domains (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    domain TEXT NOT NULL,
    available INTEGER,
    price_usd REAL,
    renew_price_usd REAL,
    registrar TEXT,
    tld TEXT,
    premium INTEGER DEFAULT 0,
    notes TEXT,
    selected INTEGER DEFAULT 0,
    purchased INTEGER DEFAULT 0,
    created_at TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS emails (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    address TEXT NOT NULL,
    display_name TEXT,
    role TEXT,
    provider TEXT,
    password_hint TEXT,
    created_at TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS socials (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    handle TEXT,
    display_name TEXT,
    url TEXT,
    status TEXT,
    bio TEXT,
    metadata TEXT,
    created_at TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS social_posts (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    platform TEXT,
    content TEXT,
    status TEXT,
    scheduled_at TEXT,
    posted_at TEXT,
    metrics TEXT,
    created_at TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS agent_status (
    project_id TEXT NOT NULL,
    agent TEXT NOT NULL,
    status TEXT,
    current_task TEXT,
    last_heartbeat TEXT,
    loop_count INTEGER DEFAULT 0,
    metadata TEXT,
    PRIMARY KEY (project_id, agent)
);

CREATE INDEX IF NOT EXISTS idx_messages_project ON messages(project_id);
CREATE INDEX IF NOT EXISTS idx_messages_to ON messages(to_agent, read);
CREATE INDEX IF NOT EXISTS idx_costs_project ON costs(project_id);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status);
"""


class SharedBrain:
    """Thread-safe SQLite store shared by all agents."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    @contextmanager
    def _cursor(self) -> Iterator[sqlite3.Cursor]:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.cursor()
                yield cur
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def _init_db(self) -> None:
        with self._cursor() as cur:
            cur.executescript(SCHEMA)

    # ── Projects ──────────────────────────────────────────────

    def create_project(self, project: Project) -> Project:
        project.updated_at = utcnow()
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO projects (
                    id, name, slug, description, budget_usd, spent_usd, stack, tone,
                    status, github_repo, vercel_url, supabase_project_id, domain,
                    created_at, updated_at, metadata
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    project.id,
                    project.name,
                    project.slug,
                    project.description,
                    project.budget_usd,
                    project.spent_usd,
                    project.stack,
                    project.tone,
                    project.status,
                    project.github_repo,
                    project.vercel_url,
                    project.supabase_project_id,
                    project.domain,
                    project.created_at.isoformat(),
                    project.updated_at.isoformat(),
                    json.dumps(project.metadata),
                ),
            )
        for agent in AgentRole:
            if agent in (AgentRole.HUMAN, AgentRole.SYSTEM):
                continue
            self.set_agent_status(
                AgentStateRecord(project_id=project.id, agent=agent, status=AgentStatus.IDLE)
            )
        return project

    def get_project(self, project_id: str) -> Project | None:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
            row = cur.fetchone()
        return self._row_to_project(row) if row else None

    def get_project_by_slug(self, slug: str) -> Project | None:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM projects WHERE slug = ? ORDER BY created_at DESC LIMIT 1", (slug,))
            row = cur.fetchone()
        return self._row_to_project(row) if row else None

    def list_projects(self) -> list[Project]:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM projects ORDER BY created_at DESC")
            rows = cur.fetchall()
        return [self._row_to_project(r) for r in rows]

    def update_project(self, project: Project) -> Project:
        project.updated_at = utcnow()
        with self._cursor() as cur:
            cur.execute(
                """
                UPDATE projects SET
                    name=?, slug=?, description=?, budget_usd=?, spent_usd=?, stack=?, tone=?,
                    status=?, github_repo=?, vercel_url=?, supabase_project_id=?, domain=?,
                    updated_at=?, metadata=?
                WHERE id=?
                """,
                (
                    project.name,
                    project.slug,
                    project.description,
                    project.budget_usd,
                    project.spent_usd,
                    project.stack,
                    project.tone,
                    project.status,
                    project.github_repo,
                    project.vercel_url,
                    project.supabase_project_id,
                    project.domain,
                    project.updated_at.isoformat(),
                    json.dumps(project.metadata),
                    project.id,
                ),
            )
        return project

    def _row_to_project(self, row: sqlite3.Row) -> Project:
        return Project(
            id=row["id"],
            name=row["name"],
            slug=row["slug"],
            description=row["description"] or "",
            budget_usd=row["budget_usd"],
            spent_usd=row["spent_usd"] or 0,
            stack=row["stack"] or "",
            tone=row["tone"] or "",
            status=row["status"],
            github_repo=row["github_repo"],
            vercel_url=row["vercel_url"],
            supabase_project_id=row["supabase_project_id"],
            domain=row["domain"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            metadata=_json(row["metadata"]),
        )

    # ── Messages ──────────────────────────────────────────────

    def send_message(self, msg: Message) -> Message:
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO messages (
                    id, project_id, from_agent, to_agent, subject, body, priority,
                    requires_reply, parent_id, payload, read, created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    msg.id,
                    msg.project_id,
                    msg.from_agent.value if isinstance(msg.from_agent, AgentRole) else msg.from_agent,
                    msg.to_agent.value if isinstance(msg.to_agent, AgentRole) else msg.to_agent,
                    msg.subject,
                    msg.body,
                    msg.priority.value if hasattr(msg.priority, "value") else msg.priority,
                    1 if msg.requires_reply else 0,
                    msg.parent_id,
                    json.dumps(msg.payload),
                    1 if msg.read else 0,
                    msg.created_at.isoformat(),
                ),
            )
        return msg

    def get_inbox(
        self,
        project_id: str,
        agent: AgentRole | str,
        unread_only: bool = False,
        limit: int = 50,
    ) -> list[Message]:
        agent_val = agent.value if isinstance(agent, AgentRole) else agent
        q = """
            SELECT * FROM messages
            WHERE project_id = ? AND (to_agent = ? OR to_agent = 'all')
        """
        params: list[Any] = [project_id, agent_val]
        if unread_only:
            q += " AND read = 0"
        q += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._cursor() as cur:
            cur.execute(q, params)
            rows = cur.fetchall()
        return [self._row_to_message(r) for r in rows]

    def mark_read(self, message_id: str) -> None:
        with self._cursor() as cur:
            cur.execute("UPDATE messages SET read = 1 WHERE id = ?", (message_id,))

    def get_thread(self, project_id: str, limit: int = 100) -> list[Message]:
        """Return the latest `limit` messages in chronological order (oldest→newest)."""
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT * FROM (
                    SELECT * FROM messages
                    WHERE project_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                ) AS recent
                ORDER BY created_at ASC
                """,
                (project_id, limit),
            )
            rows = cur.fetchall()
        return [self._row_to_message(r) for r in rows]

    def _row_to_message(self, row: sqlite3.Row) -> Message:
        return Message(
            id=row["id"],
            project_id=row["project_id"],
            from_agent=AgentRole(row["from_agent"]),
            to_agent=row["to_agent"] if row["to_agent"] == "all" else AgentRole(row["to_agent"]),
            subject=row["subject"] or "",
            body=row["body"] or "",
            priority=row["priority"] or "normal",
            requires_reply=bool(row["requires_reply"]),
            parent_id=row["parent_id"],
            payload=_json(row["payload"]),
            read=bool(row["read"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    # ── Costs & Budget ────────────────────────────────────────

    def add_cost(self, entry: CostEntry) -> CostEntry:
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO costs (
                    id, project_id, category, amount_usd, description, vendor,
                    approved, approved_by, recurring_monthly, metadata, created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    entry.id,
                    entry.project_id,
                    entry.category.value if hasattr(entry.category, "value") else entry.category,
                    entry.amount_usd,
                    entry.description,
                    entry.vendor,
                    1 if entry.approved else 0,
                    entry.approved_by,
                    1 if entry.recurring_monthly else 0,
                    json.dumps(entry.metadata),
                    entry.created_at.isoformat(),
                ),
            )
            if entry.approved:
                cur.execute(
                    "UPDATE projects SET spent_usd = spent_usd + ?, updated_at = ? WHERE id = ?",
                    (entry.amount_usd, utcnow().isoformat(), entry.project_id),
                )
        return entry

    def approve_cost(self, cost_id: str, approved_by: str = "human") -> CostEntry | None:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM costs WHERE id = ?", (cost_id,))
            row = cur.fetchone()
            if not row:
                return None
            if row["approved"]:
                return self._row_to_cost(row)
            cur.execute(
                "UPDATE costs SET approved = 1, approved_by = ? WHERE id = ?",
                (approved_by, cost_id),
            )
            cur.execute(
                "UPDATE projects SET spent_usd = spent_usd + ?, updated_at = ? WHERE id = ?",
                (row["amount_usd"], utcnow().isoformat(), row["project_id"]),
            )
            cur.execute("SELECT * FROM costs WHERE id = ?", (cost_id,))
            return self._row_to_cost(cur.fetchone())

    def list_costs(self, project_id: str, approved_only: bool = False) -> list[CostEntry]:
        q = "SELECT * FROM costs WHERE project_id = ?"
        if approved_only:
            q += " AND approved = 1"
        q += " ORDER BY created_at DESC"
        with self._cursor() as cur:
            cur.execute(q, (project_id,))
            rows = cur.fetchall()
        return [self._row_to_cost(r) for r in rows]

    def budget_snapshot(self, project_id: str, alert_threshold_pct: float = 0.85) -> BudgetSnapshot:
        project = self.get_project(project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")
        costs = self.list_costs(project_id)
        approved = [c for c in costs if c.approved]
        pending = [c for c in costs if not c.approved]
        spent = sum(c.amount_usd for c in approved)
        pending_usd = sum(c.amount_usd for c in pending)
        by_cat: dict[str, float] = {}
        for c in approved:
            key = c.category.value if hasattr(c.category, "value") else str(c.category)
            by_cat[key] = by_cat.get(key, 0) + c.amount_usd
        remaining = project.budget_usd - spent
        alert = False
        msg = ""
        if project.budget_usd > 0 and spent / project.budget_usd >= alert_threshold_pct:
            alert = True
            msg = f"Spent {spent:.2f}/{project.budget_usd:.2f} USD ({100*spent/project.budget_usd:.0f}%)"
        if remaining < pending_usd:
            alert = True
            msg = f"Pending costs ${pending_usd:.2f} exceed remaining ${remaining:.2f}"
        # Keep project.spent_usd in sync
        if abs(project.spent_usd - spent) > 0.001:
            project.spent_usd = spent
            self.update_project(project)
        return BudgetSnapshot(
            project_id=project_id,
            budget_usd=project.budget_usd,
            spent_usd=spent,
            pending_usd=pending_usd,
            remaining_usd=remaining,
            by_category=by_cat,
            alert=alert,
            alert_message=msg,
        )

    def _row_to_cost(self, row: sqlite3.Row) -> CostEntry:
        return CostEntry(
            id=row["id"],
            project_id=row["project_id"],
            category=CostCategory(row["category"]),
            amount_usd=row["amount_usd"],
            description=row["description"] or "",
            vendor=row["vendor"] or "",
            approved=bool(row["approved"]),
            approved_by=row["approved_by"],
            recurring_monthly=bool(row["recurring_monthly"]),
            metadata=_json(row["metadata"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    # ── Approvals ─────────────────────────────────────────────

    def create_approval(self, req: ApprovalRequest) -> ApprovalRequest:
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO approvals (
                    id, project_id, requested_by, action, description, amount_usd,
                    irreversible, status, options, metadata, decided_at, decision_note, created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    req.id,
                    req.project_id,
                    req.requested_by.value if isinstance(req.requested_by, AgentRole) else req.requested_by,
                    req.action,
                    req.description,
                    req.amount_usd,
                    1 if req.irreversible else 0,
                    req.status.value if hasattr(req.status, "value") else req.status,
                    json.dumps(req.options),
                    json.dumps(req.metadata),
                    req.decided_at.isoformat() if req.decided_at else None,
                    req.decision_note,
                    req.created_at.isoformat(),
                ),
            )
        return req

    def list_pending_approvals(self, project_id: str | None = None) -> list[ApprovalRequest]:
        q = "SELECT * FROM approvals WHERE status = 'pending'"
        params: list[Any] = []
        if project_id:
            q += " AND project_id = ?"
            params.append(project_id)
        q += " ORDER BY created_at ASC"
        with self._cursor() as cur:
            cur.execute(q, params)
            rows = cur.fetchall()
        return [self._row_to_approval(r) for r in rows]

    def decide_approval(
        self,
        approval_id: str,
        approved: bool,
        note: str = "",
    ) -> ApprovalRequest | None:
        status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
        now = utcnow().isoformat()
        with self._cursor() as cur:
            cur.execute(
                "UPDATE approvals SET status=?, decided_at=?, decision_note=? WHERE id=?",
                (status.value, now, note, approval_id),
            )
            cur.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,))
            row = cur.fetchone()
        return self._row_to_approval(row) if row else None

    def get_approval(self, approval_id: str) -> ApprovalRequest | None:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,))
            row = cur.fetchone()
        return self._row_to_approval(row) if row else None

    def _row_to_approval(self, row: sqlite3.Row) -> ApprovalRequest:
        return ApprovalRequest(
            id=row["id"],
            project_id=row["project_id"],
            requested_by=AgentRole(row["requested_by"]),
            action=row["action"],
            description=row["description"] or "",
            amount_usd=row["amount_usd"] or 0,
            irreversible=bool(row["irreversible"]),
            status=ApprovalStatus(row["status"]),
            options=_json(row["options"], []),
            metadata=_json(row["metadata"]),
            decided_at=datetime.fromisoformat(row["decided_at"]) if row["decided_at"] else None,
            decision_note=row["decision_note"] or "",
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    # ── Domains ───────────────────────────────────────────────

    def save_domain_options(self, project_id: str, options: list[DomainOption]) -> None:
        now = utcnow().isoformat()
        with self._cursor() as cur:
            for o in options:
                cur.execute(
                    """
                    INSERT INTO domains (
                        project_id, domain, available, price_usd, renew_price_usd,
                        registrar, tld, premium, notes, created_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        project_id,
                        o.domain,
                        1 if o.available else 0,
                        o.price_usd,
                        o.renew_price_usd,
                        o.registrar,
                        o.tld or o.domain.rsplit(".", 1)[-1],
                        1 if o.premium else 0,
                        o.notes,
                        now,
                    ),
                )

    def list_domain_options(self, project_id: str) -> list[DomainOption]:
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM domains WHERE project_id = ? ORDER BY price_usd ASC",
                (project_id,),
            )
            rows = cur.fetchall()
        return [
            DomainOption(
                domain=r["domain"],
                available=bool(r["available"]),
                price_usd=r["price_usd"] or 0,
                renew_price_usd=r["renew_price_usd"],
                registrar=r["registrar"] or "",
                tld=r["tld"] or "",
                premium=bool(r["premium"]),
                notes=r["notes"] or "",
            )
            for r in rows
        ]

    def mark_domain_purchased(self, project_id: str, domain: str) -> None:
        with self._cursor() as cur:
            cur.execute(
                "UPDATE domains SET purchased = 1, selected = 1 WHERE project_id = ? AND domain = ?",
                (project_id, domain),
            )
            cur.execute(
                "UPDATE projects SET domain = ?, updated_at = ? WHERE id = ?",
                (domain, utcnow().isoformat(), project_id),
            )

    # ── Emails ────────────────────────────────────────────────

    def add_email(self, email: EmailAccount) -> EmailAccount:
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO emails (id, project_id, address, display_name, role, provider, password_hint, created_at)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    email.id,
                    email.project_id,
                    email.address,
                    email.display_name,
                    email.role,
                    email.provider,
                    email.password_hint,
                    email.created_at.isoformat(),
                ),
            )
        return email

    def list_emails(self, project_id: str) -> list[EmailAccount]:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM emails WHERE project_id = ?", (project_id,))
            rows = cur.fetchall()
        return [
            EmailAccount(
                id=r["id"],
                project_id=r["project_id"],
                address=r["address"],
                display_name=r["display_name"] or "",
                role=r["role"] or "",
                provider=r["provider"] or "mock",
                password_hint=r["password_hint"] or "",
                created_at=datetime.fromisoformat(r["created_at"]),
            )
            for r in rows
        ]

    # ── Socials ───────────────────────────────────────────────

    def add_social(self, account: SocialAccount) -> SocialAccount:
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO socials (
                    id, project_id, platform, handle, display_name, url, status, bio, metadata, created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    account.id,
                    account.project_id,
                    account.platform,
                    account.handle,
                    account.display_name,
                    account.url,
                    account.status,
                    account.bio,
                    json.dumps(account.metadata),
                    account.created_at.isoformat(),
                ),
            )
        return account

    def list_socials(self, project_id: str) -> list[SocialAccount]:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM socials WHERE project_id = ?", (project_id,))
            rows = cur.fetchall()
        return [
            SocialAccount(
                id=r["id"],
                project_id=r["project_id"],
                platform=r["platform"],
                handle=r["handle"] or "",
                display_name=r["display_name"] or "",
                url=r["url"] or "",
                status=r["status"] or "",
                bio=r["bio"] or "",
                metadata=_json(r["metadata"]),
                created_at=datetime.fromisoformat(r["created_at"]),
            )
            for r in rows
        ]

    def add_social_post(self, post: SocialPost) -> SocialPost:
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO social_posts (
                    id, project_id, platform, content, status, scheduled_at, posted_at, metrics, created_at
                ) VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    post.id,
                    post.project_id,
                    post.platform,
                    post.content,
                    post.status,
                    post.scheduled_at.isoformat() if post.scheduled_at else None,
                    post.posted_at.isoformat() if post.posted_at else None,
                    json.dumps(post.metrics),
                    post.created_at.isoformat(),
                ),
            )
        return post

    def list_social_posts(self, project_id: str) -> list[SocialPost]:
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM social_posts WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,),
            )
            rows = cur.fetchall()
        return [
            SocialPost(
                id=r["id"],
                project_id=r["project_id"],
                platform=r["platform"] or "",
                content=r["content"] or "",
                status=r["status"] or "draft",
                scheduled_at=datetime.fromisoformat(r["scheduled_at"]) if r["scheduled_at"] else None,
                posted_at=datetime.fromisoformat(r["posted_at"]) if r["posted_at"] else None,
                metrics=_json(r["metrics"]),
                created_at=datetime.fromisoformat(r["created_at"]),
            )
            for r in rows
        ]

    # ── Agent status ──────────────────────────────────────────

    def set_agent_status(self, state: AgentStateRecord) -> None:
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO agent_status (
                    project_id, agent, status, current_task, last_heartbeat, loop_count, metadata
                ) VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(project_id, agent) DO UPDATE SET
                    status=excluded.status,
                    current_task=excluded.current_task,
                    last_heartbeat=excluded.last_heartbeat,
                    loop_count=excluded.loop_count,
                    metadata=excluded.metadata
                """,
                (
                    state.project_id,
                    state.agent.value if isinstance(state.agent, AgentRole) else state.agent,
                    state.status.value if isinstance(state.status, AgentStatus) else state.status,
                    state.current_task,
                    state.last_heartbeat.isoformat(),
                    state.loop_count,
                    json.dumps(state.metadata),
                ),
            )

    def get_agent_statuses(self, project_id: str) -> list[AgentStateRecord]:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM agent_status WHERE project_id = ?", (project_id,))
            rows = cur.fetchall()
        return [
            AgentStateRecord(
                project_id=r["project_id"],
                agent=AgentRole(r["agent"]),
                status=AgentStatus(r["status"]) if r["status"] else AgentStatus.IDLE,
                current_task=r["current_task"] or "",
                last_heartbeat=datetime.fromisoformat(r["last_heartbeat"])
                if r["last_heartbeat"]
                else utcnow(),
                loop_count=r["loop_count"] or 0,
                metadata=_json(r["metadata"]),
            )
            for r in rows
        ]

    def bump_loop(self, project_id: str, agent: AgentRole, task: str = "") -> int:
        statuses = {s.agent: s for s in self.get_agent_statuses(project_id)}
        current = statuses.get(agent) or AgentStateRecord(project_id=project_id, agent=agent)
        current.loop_count += 1
        current.status = AgentStatus.RUNNING
        current.current_task = task or current.current_task
        current.last_heartbeat = utcnow()
        self.set_agent_status(current)
        return current.loop_count
