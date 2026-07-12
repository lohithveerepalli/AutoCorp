"""Base agent with messaging, status, and optional ReAct loop."""

from __future__ import annotations

from typing import Any

from autocorp.core.config import UserConfig, load_user_config
from autocorp.core.llm import get_chat_model
from autocorp.core.messaging import MessageBus
from autocorp.core.models import AgentRole, AgentStateRecord, AgentStatus
from autocorp.db.brain import SharedBrain
from autocorp.ui.console import AgentConsole


class BaseAgent:
    role: AgentRole = AgentRole.SYSTEM
    system_prompt: str = "You are an AutoCorp agent."

    def __init__(
        self,
        brain: SharedBrain,
        bus: MessageBus,
        user_config: UserConfig | None = None,
    ) -> None:
        self.brain = brain
        self.bus = bus
        self.user_config = user_config or load_user_config()
        self.ui = AgentConsole(self.role)
        self._llm = None

    @property
    def llm(self):
        if self._llm is None:
            try:
                self._llm = get_chat_model(self.role.value, self.user_config)  # type: ignore[arg-type]
            except Exception as e:
                self.ui.warn(f"LLM unavailable ({e}); running deterministic tools only")
                self._llm = None
        return self._llm

    def set_status(
        self,
        project_id: str,
        status: AgentStatus,
        task: str = "",
        loop_count: int | None = None,
    ) -> None:
        current = None
        for s in self.brain.get_agent_statuses(project_id):
            if s.agent == self.role:
                current = s
                break
        rec = current or AgentStateRecord(project_id=project_id, agent=self.role)
        rec.status = status
        if task:
            rec.current_task = task
        if loop_count is not None:
            rec.loop_count = loop_count
        from autocorp.core.models import utcnow

        rec.last_heartbeat = utcnow()
        self.brain.set_agent_status(rec)

    def say(
        self,
        project_id: str,
        to: AgentRole | str,
        subject: str,
        body: str,
        **kwargs: Any,
    ):
        self.ui.log(f"→ {to}: {subject}")
        return self.bus.publish(
            project_id=project_id,
            from_agent=self.role,
            to_agent=to,
            subject=subject,
            body=body,
            **kwargs,
        )

    def think(self, prompt: str) -> str:
        """Optional LLM reasoning; falls back to empty on failure."""
        if self.llm is None:
            return ""
        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            result = self.llm.invoke(
                [
                    SystemMessage(content=self.system_prompt),
                    HumanMessage(content=prompt),
                ]
            )
            content = result.content
            if isinstance(content, list):
                return " ".join(str(c) for c in content)
            return str(content)
        except Exception as e:
            self.ui.warn(f"LLM call failed: {e}")
            return ""

    def run_once(self, project_id: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Single autonomous loop iteration — override in subclasses."""
        raise NotImplementedError

    def process_inbox(self, project_id: str) -> list[str]:
        notes = []
        for msg in self.bus.inbox(project_id, self.role, unread_only=True):
            notes.append(f"{msg.from_agent.value}: {msg.subject} — {msg.body[:200]}")
            self.bus.mark_read(msg.id)
        return notes
