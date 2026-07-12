"""CEO → Agent chat service with per-company, per-agent persistence."""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator
from uuid import uuid4

from autocorp.core.config import get_settings, load_user_config, resolve_model_for_role
from autocorp.core.models import AgentRole
from autocorp.db.brain import SharedBrain
from autocorp.ui.design import AGENT_ROLES, QUICK_ACTION_CHIPS


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_msg_id() -> str:
    return f"chat_{uuid4().hex[:12]}"


@dataclass
class ChatMessage:
    id: str
    project_id: str
    agent: str
    role: str  # user | agent | system
    content: str
    model: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_chats (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    agent TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    model TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_agent_chats_thread
    ON agent_chats(project_id, agent, created_at);
"""


class AgentChatService:
    """Persist and drive CEO↔agent conversations.

    Persistence is keyed by (project_id, agent). LLM boundary is injectable
    for tests via `reply_fn`.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        settings = get_settings()
        self.db_path = Path(db_path) if db_path else settings.data_dir / "agent_chats.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.executescript(SCHEMA)
                conn.commit()
            finally:
                conn.close()

    def list_messages(self, project_id: str, agent: str, limit: int = 500) -> list[ChatMessage]:
        """Return the latest `limit` messages in chronological order (oldest→newest)."""
        agent = agent.lower()
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    """
                    SELECT * FROM (
                        SELECT * FROM agent_chats
                        WHERE project_id = ? AND agent = ?
                        ORDER BY created_at DESC
                        LIMIT ?
                    ) AS recent
                    ORDER BY created_at ASC
                    """,
                    (project_id, agent, limit),
                )
                rows = cur.fetchall()
            finally:
                conn.close()
        return [self._row(r) for r in rows]

    def append_message(
        self,
        project_id: str,
        agent: str,
        role: str,
        content: str,
        model: str = "",
    ) -> ChatMessage:
        agent = agent.lower()
        if agent not in AGENT_ROLES:
            raise ValueError(f"Unknown agent: {agent}")
        if role not in ("user", "agent", "system"):
            raise ValueError(f"Unknown role: {role}")
        msg = ChatMessage(
            id=new_msg_id(),
            project_id=project_id,
            agent=agent,
            role=role,
            content=content,
            model=model or "",
            created_at=utcnow_iso(),
        )
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO agent_chats (id, project_id, agent, role, content, model, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        msg.id,
                        msg.project_id,
                        msg.agent,
                        msg.role,
                        msg.content,
                        msg.model,
                        msg.created_at,
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        return msg

    def clear_thread(self, project_id: str, agent: str) -> int:
        """Clear only this company+agent thread. Returns deleted count."""
        agent = agent.lower()
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "DELETE FROM agent_chats WHERE project_id = ? AND agent = ?",
                    (project_id, agent),
                )
                conn.commit()
                return cur.rowcount or 0
            finally:
                conn.close()

    def export_thread(
        self,
        project_id: str,
        agent: str,
        fmt: str = "markdown",
    ) -> str:
        msgs = self.list_messages(project_id, agent)
        if fmt == "json":
            return json.dumps([m.to_dict() for m in msgs], indent=2)
        # markdown
        lines = [f"# Chat · {agent} · {project_id}", ""]
        for m in msgs:
            who = "CEO" if m.role == "user" else agent.title()
            model = f" ({m.model})" if m.model and m.role == "agent" else ""
            lines.append(f"**{who}{model}** · `{m.created_at}`")
            lines.append("")
            lines.append(m.content)
            lines.append("")
            lines.append("---")
            lines.append("")
        return "\n".join(lines).strip() + "\n"

    def model_for_agent(self, agent: str) -> str:
        cfg = load_user_config()
        role = agent.lower()
        if role not in AGENT_ROLES:
            return cfg.models.brain
        return resolve_model_for_role(role, cfg)  # type: ignore[arg-type]

    def build_system_prompt(self, agent: str, project: Any | None) -> str:
        agent = agent.lower()
        base = {
            "brain": "You are The Brain of AutoCorp — CTO and full product owner.",
            "operator": "You are The Operator of AutoCorp — infrastructure and ops lead.",
            "marketer": "You are The Marketer of AutoCorp — CMO for brand and growth.",
            "accountant": "You are The Accountant of AutoCorp — CFO for budget and P&L.",
        }.get(agent, "You are an AutoCorp executive agent.")
        ctx = ""
        if project is not None:
            ctx = (
                f"\n\nCurrent company context:\n"
                f"- Name: {getattr(project, 'name', '')}\n"
                f"- Description: {getattr(project, 'description', '')}\n"
                f"- Budget: ${getattr(project, 'budget_usd', 0):.2f}\n"
                f"- Spent: ${getattr(project, 'spent_usd', 0):.2f}\n"
                f"- Domain: {getattr(project, 'domain', None) or 'pending'}\n"
                f"- Status: {getattr(project, 'status', '')}\n"
                f"- Stack: {getattr(project, 'stack', '')}\n"
                f"- GitHub: {getattr(project, 'github_repo', None) or '—'}\n"
                f"- Vercel: {getattr(project, 'vercel_url', None) or '—'}\n"
            )
        return (
            f"{base}\nYou are speaking directly with the human CEO. "
            f"Be concise, executive, and actionable. Use markdown sparingly."
            f"{ctx}"
        )

    def default_reply_fn(
        self,
        agent: str,
        project: Any | None,
        history: list[ChatMessage],
        user_text: str,
        on_token: Callable[[str], None] | None = None,
    ) -> str:
        """Call configured LLM; optional token stream via on_token."""
        model_id = self.model_for_agent(agent)
        system = self.build_system_prompt(agent, project)
        try:
            from autocorp.core.llm import get_chat_model
            from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

            llm = get_chat_model(agent)  # type: ignore[arg-type]
            lc_messages: list[Any] = [SystemMessage(content=system)]
            for m in history[-20:]:
                if m.role == "user":
                    lc_messages.append(HumanMessage(content=m.content))
                elif m.role == "agent":
                    lc_messages.append(AIMessage(content=m.content))
            lc_messages.append(HumanMessage(content=user_text))

            # Prefer streaming when possible
            if on_token is not None and hasattr(llm, "stream"):
                chunks: list[str] = []
                try:
                    for chunk in llm.stream(lc_messages):
                        piece = getattr(chunk, "content", None)
                        if piece is None:
                            continue
                        if isinstance(piece, list):
                            piece = "".join(str(x) for x in piece)
                        piece = str(piece)
                        if piece:
                            chunks.append(piece)
                            on_token(piece)
                    if chunks:
                        return "".join(chunks)
                except Exception:
                    pass

            result = llm.invoke(lc_messages)
            content = result.content
            if isinstance(content, list):
                return " ".join(str(c) for c in content)
            text = str(content)
            if on_token:
                on_token(text)
            return text
        except Exception as e:
            fallback = (
                f"[{agent.title()}] I'm online but the LLM call failed ({e}). "
                f"Configured model: {model_id}. "
                f"I still received your note: “{user_text[:200]}”. "
                "Add API keys in Settings or use a local Ollama model."
            )
            if on_token:
                on_token(fallback)
            return fallback

    def send_user_message(
        self,
        project_id: str,
        agent: str,
        content: str,
        *,
        brain: SharedBrain | None = None,
        reply_fn: Callable[..., str] | None = None,
        on_token: Callable[[str], None] | None = None,
    ) -> tuple[ChatMessage, ChatMessage]:
        """Store user message, generate agent reply, store agent message."""
        agent = agent.lower()
        text = (content or "").strip()
        if not text:
            raise ValueError("Message cannot be empty")

        model_id = self.model_for_agent(agent)
        user_msg = self.append_message(project_id, agent, "user", text)

        project = None
        if brain is not None:
            project = brain.get_project(project_id)

        history = self.list_messages(project_id, agent)
        # history includes the just-appended user message; reply_fn may use prior
        prior = [m for m in history if m.id != user_msg.id]

        if reply_fn is None:
            reply_text = self.default_reply_fn(
                agent, project, prior, text, on_token=on_token
            )
        else:
            # Custom reply_fn may accept optional on_token
            try:
                reply_text = reply_fn(agent, project, prior, text, on_token)
            except TypeError:
                reply_text = reply_fn(agent, project, prior, text)
        agent_msg = self.append_message(
            project_id, agent, "agent", reply_text, model=model_id
        )
        return user_msg, agent_msg

    def chip_prompt(self, chip_id: str) -> str | None:
        for c in QUICK_ACTION_CHIPS:
            if c["id"] == chip_id:
                return c["prompt"]
        return None

    def apply_quick_action(
        self,
        project_id: str,
        agent: str,
        chip_id: str,
        *,
        brain: SharedBrain | None = None,
        reply_fn: Callable[..., str] | None = None,
        on_token: Callable[[str], None] | None = None,
    ) -> tuple[ChatMessage, ChatMessage]:
        """Resolve a chip id to its prompt and send as a CEO message (auto-send).

        Independent of Streamlit text_area widget state — chips always persist.
        """
        prompt = self.chip_prompt(chip_id)
        if not prompt:
            raise ValueError(f"Unknown quick-action chip: {chip_id}")
        return self.send_user_message(
            project_id,
            agent,
            prompt,
            brain=brain,
            reply_fn=reply_fn,
            on_token=on_token,
        )

    @staticmethod
    def _row(r: sqlite3.Row) -> ChatMessage:
        return ChatMessage(
            id=r["id"],
            project_id=r["project_id"],
            agent=r["agent"],
            role=r["role"],
            content=r["content"],
            model=r["model"] or "",
            created_at=r["created_at"],
        )
