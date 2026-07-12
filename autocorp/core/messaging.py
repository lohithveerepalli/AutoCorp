"""Cross-agent messaging bus backed by SharedBrain."""

from __future__ import annotations

from typing import Callable

from autocorp.core.models import AgentRole, Message, MessagePriority
from autocorp.db.brain import SharedBrain


class MessageBus:
    """Pub/sub style bus over SQLite for multi-agent coordination."""

    def __init__(self, brain: SharedBrain) -> None:
        self.brain = brain
        self._listeners: list[Callable[[Message], None]] = []

    def subscribe(self, callback: Callable[[Message], None]) -> None:
        self._listeners.append(callback)

    def publish(
        self,
        project_id: str,
        from_agent: AgentRole,
        to_agent: AgentRole | str,
        subject: str,
        body: str,
        priority: MessagePriority = MessagePriority.NORMAL,
        requires_reply: bool = False,
        payload: dict | None = None,
        parent_id: str | None = None,
    ) -> Message:
        msg = Message(
            project_id=project_id,
            from_agent=from_agent,
            to_agent=to_agent,  # type: ignore[arg-type]
            subject=subject,
            body=body,
            priority=priority,
            requires_reply=requires_reply,
            payload=payload or {},
            parent_id=parent_id,
        )
        self.brain.send_message(msg)
        for cb in self._listeners:
            try:
                cb(msg)
            except Exception:
                pass
        return msg

    def broadcast(
        self,
        project_id: str,
        from_agent: AgentRole,
        subject: str,
        body: str,
        **kwargs,
    ) -> Message:
        return self.publish(
            project_id=project_id,
            from_agent=from_agent,
            to_agent="all",
            subject=subject,
            body=body,
            **kwargs,
        )

    def inbox(self, project_id: str, agent: AgentRole, unread_only: bool = True) -> list[Message]:
        return self.brain.get_inbox(project_id, agent, unread_only=unread_only)

    def mark_read(self, message_id: str) -> None:
        self.brain.mark_read(message_id)

    def reply(
        self,
        original: Message,
        from_agent: AgentRole,
        body: str,
        subject: str | None = None,
        **kwargs,
    ) -> Message:
        return self.publish(
            project_id=original.project_id,
            from_agent=from_agent,
            to_agent=original.from_agent,
            subject=subject or f"Re: {original.subject}",
            body=body,
            parent_id=original.id,
            **kwargs,
        )
