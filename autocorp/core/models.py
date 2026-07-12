"""Domain models for AutoCorp."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str = "") -> str:
    uid = uuid4().hex[:12]
    return f"{prefix}{uid}" if prefix else uid


class AgentRole(str, Enum):
    BRAIN = "brain"
    OPERATOR = "operator"
    MARKETER = "marketer"
    ACCOUNTANT = "accountant"
    HUMAN = "human"
    SYSTEM = "system"


class AgentStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    BLOCKED = "blocked"
    ERROR = "error"
    DONE = "done"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class MessagePriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class CostCategory(str, Enum):
    DOMAIN = "domain"
    EMAIL = "email"
    HOSTING = "hosting"
    LLM_API = "llm_api"
    SOCIAL_ADS = "social_ads"
    TOOLS = "tools"
    STRIPE_FEES = "stripe_fees"
    OTHER = "other"


class CompanyBrief(BaseModel):
    """CEO launch brief — the only human input required to start."""

    name: str
    description: str
    budget_usd: float = 500.0
    stack_preference: str = "Next.js + Supabase + Stripe + Vercel"
    tone: str = "clean, professional"
    extra: dict[str, Any] = Field(default_factory=dict)


class Project(BaseModel):
    id: str = Field(default_factory=lambda: new_id("proj_"))
    name: str
    slug: str = ""
    description: str = ""
    budget_usd: float = 500.0
    spent_usd: float = 0.0
    stack: str = "Next.js + Supabase + Stripe + Vercel"
    tone: str = "clean, professional"
    status: str = "launching"  # launching | active | paused | archived
    github_repo: str | None = None
    vercel_url: str | None = None
    supabase_project_id: str | None = None
    domain: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        if not self.slug:
            self.slug = (
                self.name.lower()
                .replace(" ", "-")
                .replace("_", "-")
                .replace(".", "")
            )


class Message(BaseModel):
    id: str = Field(default_factory=lambda: new_id("msg_"))
    project_id: str
    from_agent: AgentRole
    to_agent: AgentRole | Literal["all"]
    subject: str
    body: str
    priority: MessagePriority = MessagePriority.NORMAL
    requires_reply: bool = False
    parent_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    read: bool = False
    created_at: datetime = Field(default_factory=utcnow)


class CostEntry(BaseModel):
    id: str = Field(default_factory=lambda: new_id("cost_"))
    project_id: str
    category: CostCategory
    amount_usd: float
    description: str
    vendor: str = ""
    approved: bool = False
    approved_by: str | None = None
    recurring_monthly: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)


class BudgetSnapshot(BaseModel):
    project_id: str
    budget_usd: float
    spent_usd: float
    pending_usd: float
    remaining_usd: float
    by_category: dict[str, float] = Field(default_factory=dict)
    alert: bool = False
    alert_message: str = ""


class ApprovalRequest(BaseModel):
    id: str = Field(default_factory=lambda: new_id("appr_"))
    project_id: str
    requested_by: AgentRole
    action: str
    description: str
    amount_usd: float = 0.0
    irreversible: bool = False
    status: ApprovalStatus = ApprovalStatus.PENDING
    options: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    decided_at: datetime | None = None
    decision_note: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class DomainOption(BaseModel):
    domain: str
    available: bool
    price_usd: float
    renew_price_usd: float | None = None
    registrar: str
    tld: str = ""
    premium: bool = False
    notes: str = ""


class EmailAccount(BaseModel):
    id: str = Field(default_factory=lambda: new_id("email_"))
    project_id: str
    address: str
    display_name: str
    role: str  # company | brain | operator | marketer | accountant | custom
    provider: str = "mock"
    password_hint: str = ""  # never store real passwords in plain text in prod
    created_at: datetime = Field(default_factory=utcnow)


class SocialAccount(BaseModel):
    id: str = Field(default_factory=lambda: new_id("soc_"))
    project_id: str
    platform: str  # x | linkedin | instagram | tiktok
    handle: str
    display_name: str
    url: str = ""
    status: str = "pending_approval"  # pending_approval | active | mock | failed
    bio: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)


class SocialPost(BaseModel):
    id: str = Field(default_factory=lambda: new_id("post_"))
    project_id: str
    platform: str
    content: str
    status: str = "draft"  # draft | scheduled | posted | failed
    scheduled_at: datetime | None = None
    posted_at: datetime | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)


class AgentStateRecord(BaseModel):
    project_id: str
    agent: AgentRole
    status: AgentStatus = AgentStatus.IDLE
    current_task: str = ""
    last_heartbeat: datetime = Field(default_factory=utcnow)
    loop_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
