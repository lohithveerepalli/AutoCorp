"""AgentChatService — persist / clear / export / send (shipped path)."""

from pathlib import Path

import pytest

from autocorp.core.models import Project
from autocorp.db.brain import SharedBrain
from autocorp.ui.chat_service import AgentChatService
from autocorp.ui.design import QUICK_ACTION_CHIPS


@pytest.fixture
def chat(tmp_path: Path) -> AgentChatService:
    return AgentChatService(tmp_path / "chats.db")


@pytest.fixture
def project(tmp_path: Path) -> Project:
    brain = SharedBrain(tmp_path / "brain.db")
    return brain.create_project(
        Project(name="FocusFlow", description="Pomodoro app", budget_usd=450)
    )


def test_persist_keyed_by_company_and_agent(chat: AgentChatService, project: Project) -> None:
    chat.append_message(project.id, "brain", "user", "Hello Brain")
    chat.append_message(project.id, "brain", "agent", "Hello CEO", model="gpt-4o")
    chat.append_message(project.id, "operator", "user", "Hello Ops")

    brain_msgs = chat.list_messages(project.id, "brain")
    ops_msgs = chat.list_messages(project.id, "operator")
    assert len(brain_msgs) == 2
    assert len(ops_msgs) == 1
    assert brain_msgs[0].content == "Hello Brain"
    assert brain_msgs[1].role == "agent"


def test_clear_only_that_thread(chat: AgentChatService, project: Project) -> None:
    chat.append_message(project.id, "brain", "user", "A")
    chat.append_message(project.id, "marketer", "user", "B")
    deleted = chat.clear_thread(project.id, "brain")
    assert deleted == 1
    assert chat.list_messages(project.id, "brain") == []
    assert len(chat.list_messages(project.id, "marketer")) == 1


def test_export_markdown_and_json(chat: AgentChatService, project: Project) -> None:
    chat.append_message(project.id, "accountant", "user", "Show budget")
    chat.append_message(project.id, "accountant", "agent", "Budget is $450", model="gpt-4o")
    md = chat.export_thread(project.id, "accountant", fmt="markdown")
    assert "Show budget" in md
    assert "Budget is $450" in md
    assert "accountant" in md.lower()
    js = chat.export_thread(project.id, "accountant", fmt="json")
    assert "Show budget" in js


def test_send_user_message_roundtrip(chat: AgentChatService, project: Project, tmp_path: Path) -> None:
    brain = SharedBrain(tmp_path / "brain2.db")
    # re-create same id project isn't needed; pass None project via brain miss is ok
    tokens: list[str] = []

    def stub_reply(agent, proj, history, text, on_token=None):
        reply = f"ACK:{agent}:{text}"
        if on_token:
            on_token(reply)
        return reply

    user_msg, agent_msg = chat.send_user_message(
        project.id,
        "brain",
        "Propose next steps",
        brain=brain,
        reply_fn=stub_reply,
        on_token=lambda t: tokens.append(t),
    )
    assert user_msg.role == "user"
    assert agent_msg.role == "agent"
    assert "Propose next steps" in agent_msg.content or agent_msg.content.startswith("ACK:")
    assert tokens  # stream hook invoked
    loaded = chat.list_messages(project.id, "brain")
    assert len(loaded) == 2
    assert loaded[0].content == "Propose next steps"
    assert loaded[1].content == agent_msg.content


def test_quick_action_chips_present() -> None:
    labels = {c["label"] for c in QUICK_ACTION_CHIPS}
    assert "Review last code" in labels
    assert "Show budget" in labels
    assert "Propose next steps" in labels


def test_model_for_agent_uses_config(chat: AgentChatService) -> None:
    mid = chat.model_for_agent("brain")
    assert isinstance(mid, str) and len(mid) > 0


def test_list_messages_returns_latest_n(chat: AgentChatService, project: Project) -> None:
    for i in range(5):
        chat.append_message(project.id, "brain", "user", f"msg-{i}")
    latest = chat.list_messages(project.id, "brain", limit=3)
    assert len(latest) == 3
    assert [m.content for m in latest] == ["msg-2", "msg-3", "msg-4"]


def test_apply_quick_action_persists_chip_prompt(
    chat: AgentChatService, project: Project, tmp_path: Path
) -> None:
    brain = SharedBrain(tmp_path / "brain_chip.db")

    def stub(agent, proj, history, text, on_token=None):
        return f"ok:{text[:40]}"

    for chip in QUICK_ACTION_CHIPS:
        chat.clear_thread(project.id, "accountant")
        user_msg, agent_msg = chat.apply_quick_action(
            project.id,
            "accountant",
            chip["id"],
            brain=brain,
            reply_fn=stub,
        )
        assert user_msg.content == chip["prompt"]
        assert user_msg.role == "user"
        assert agent_msg.role == "agent"
        loaded = chat.list_messages(project.id, "accountant")
        assert loaded[0].content == chip["prompt"]
