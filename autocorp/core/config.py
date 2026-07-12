"""Configuration: environment variables + interactive user config."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# ---------------------------------------------------------------------------
# Model catalogs & estimated pricing (USD per 1M tokens, input/output avg)
# ---------------------------------------------------------------------------

MODEL_CATALOG: dict[str, dict[str, Any]] = {
    # Anthropic (Brain)
    "claude-sonnet-4-5": {
        "provider": "anthropic",
        "label": "Claude Sonnet 4.5",
        "input_per_m": 3.0,
        "output_per_m": 15.0,
        "roles": ["brain", "operator", "marketer", "accountant"],
    },
    "claude-opus-4-5": {
        "provider": "anthropic",
        "label": "Claude Opus 4.5",
        "input_per_m": 15.0,
        "output_per_m": 75.0,
        "roles": ["brain"],
    },
    "claude-haiku-4-5": {
        "provider": "anthropic",
        "label": "Claude Haiku 4.5",
        "input_per_m": 1.0,
        "output_per_m": 5.0,
        "roles": ["operator", "marketer", "accountant"],
    },
    # Aliases for common IDs
    "claude-sonnet-4-20250514": {
        "provider": "anthropic",
        "label": "Claude Sonnet 4 (legacy id)",
        "input_per_m": 3.0,
        "output_per_m": 15.0,
        "roles": ["brain", "operator", "marketer", "accountant"],
    },
    # OpenAI
    "gpt-4o": {
        "provider": "openai",
        "label": "GPT-4o",
        "input_per_m": 2.5,
        "output_per_m": 10.0,
        "roles": ["brain", "operator", "marketer", "accountant"],
    },
    "gpt-4o-mini": {
        "provider": "openai",
        "label": "GPT-4o Mini",
        "input_per_m": 0.15,
        "output_per_m": 0.6,
        "roles": ["operator", "marketer", "accountant"],
    },
    "o1": {
        "provider": "openai",
        "label": "OpenAI o1",
        "input_per_m": 15.0,
        "output_per_m": 60.0,
        "roles": ["brain", "accountant"],
    },
    "o1-mini": {
        "provider": "openai",
        "label": "OpenAI o1-mini",
        "input_per_m": 3.0,
        "output_per_m": 12.0,
        "roles": ["brain", "operator", "accountant"],
    },
    # DeepSeek
    "deepseek-chat": {
        "provider": "deepseek",
        "label": "DeepSeek V3 Chat",
        "input_per_m": 0.27,
        "output_per_m": 1.10,
        "roles": ["brain", "operator", "marketer", "accountant"],
        "base_url": "https://api.deepseek.com",
    },
    "deepseek-reasoner": {
        "provider": "deepseek",
        "label": "DeepSeek R1 Reasoner",
        "input_per_m": 0.55,
        "output_per_m": 2.19,
        "roles": ["brain", "accountant"],
        "base_url": "https://api.deepseek.com",
    },
    # OpenRouter (routing models)
    "openrouter/auto": {
        "provider": "openrouter",
        "label": "OpenRouter Auto",
        "input_per_m": 1.0,
        "output_per_m": 3.0,
        "roles": ["brain", "operator", "marketer", "accountant"],
        "base_url": "https://openrouter.ai/api/v1",
    },
    "openrouter/anthropic/claude-sonnet-4": {
        "provider": "openrouter",
        "label": "OpenRouter → Claude Sonnet 4",
        "input_per_m": 3.0,
        "output_per_m": 15.0,
        "roles": ["brain", "operator", "marketer", "accountant"],
        "base_url": "https://openrouter.ai/api/v1",
    },
    # Local Ollama
    "ollama/llama3.2": {
        "provider": "ollama",
        "label": "Ollama Llama 3.2 (local)",
        "input_per_m": 0.0,
        "output_per_m": 0.0,
        "roles": ["brain", "operator", "marketer", "accountant"],
    },
    "ollama/qwen2.5-coder": {
        "provider": "ollama",
        "label": "Ollama Qwen2.5 Coder (local)",
        "input_per_m": 0.0,
        "output_per_m": 0.0,
        "roles": ["brain"],
    },
    "ollama/mistral": {
        "provider": "ollama",
        "label": "Ollama Mistral (local)",
        "input_per_m": 0.0,
        "output_per_m": 0.0,
        "roles": ["operator", "marketer", "accountant"],
    },
}

# Token usage assumptions per company launch (rough, for cost estimates)
USAGE_PROFILES: dict[str, dict[str, int]] = {
    "light": {
        "label": "Light (1 small company / month)",
        "input_tokens": 800_000,
        "output_tokens": 400_000,
        "companies": 1,
    },
    "medium": {
        "label": "Medium (3 companies / month)",
        "input_tokens": 3_000_000,
        "output_tokens": 1_500_000,
        "companies": 3,
    },
    "heavy": {
        "label": "Heavy (10 companies / month)",
        "input_tokens": 12_000_000,
        "output_tokens": 6_000_000,
        "companies": 10,
    },
}

AgentRoleName = Literal["brain", "operator", "marketer", "accountant"]


class AgentModelConfig(BaseModel):
    """Per-agent model selection."""

    brain: str = "claude-sonnet-4-5"
    operator: str = "gpt-4o"
    marketer: str = "gpt-4o"
    accountant: str = "gpt-4o"


class UserConfig(BaseModel):
    """Persisted interactive configuration from `autocorp setup`."""

    models: AgentModelConfig = Field(default_factory=AgentModelConfig)
    budget_alert_usd: float = 50.0
    default_company_budget_usd: float = 500.0
    require_human_approval: bool = True
    usage_profile: Literal["light", "medium", "heavy"] = "medium"
    preferred_registrars: list[str] = Field(
        default_factory=lambda: ["porkbun", "namecheap", "cloudflare"]
    )
    setup_completed: bool = False


class Settings(BaseSettings):
    """Environment-backed settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # LLM keys
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    openrouter_api_key: str = ""
    deepseek_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"

    # Default models (env overrides; user config takes precedence when set)
    brain_model: str = "claude-sonnet-4-5"
    operator_model: str = "gpt-4o"
    marketer_model: str = "gpt-4o"
    accountant_model: str = "gpt-4o"

    # GitHub
    github_token: str = ""
    github_username: str = ""
    github_org: str = ""

    # Vercel
    vercel_token: str = ""
    vercel_team_id: str = ""

    # Supabase
    supabase_access_token: str = ""
    supabase_org_id: str = ""

    # Domains
    namecheap_api_user: str = ""
    namecheap_api_key: str = ""
    namecheap_client_ip: str = ""
    namecheap_sandbox: bool = True
    porkbun_api_key: str = ""
    porkbun_secret_key: str = ""
    cloudflare_api_token: str = ""
    cloudflare_account_id: str = ""

    # Email
    google_workspace_admin_email: str = ""
    google_service_account_json: str = ""

    # Stripe
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""

    # Social
    x_api_key: str = ""
    x_api_secret: str = ""
    x_access_token: str = ""
    x_access_secret: str = ""
    linkedin_access_token: str = ""
    instagram_access_token: str = ""
    tiktok_access_token: str = ""
    auto_approve_social: bool = False

    # Runtime
    autocorp_db_path: str = "./data/autocorp.db"
    autocorp_data_dir: str = "./data"
    autocorp_require_human_approval: bool = True
    autocorp_log_level: str = "INFO"
    autocorp_budget_alert_usd: float = 50.0

    @property
    def db_path(self) -> Path:
        return Path(self.autocorp_db_path).expanduser().resolve()

    @property
    def data_dir(self) -> Path:
        p = Path(self.autocorp_data_dir).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def config_path(self) -> Path:
        return self.data_dir / "config.json"


def project_root() -> Path:
    """Return AutoCorp package project root (repo root when installed editable)."""
    return Path(__file__).resolve().parents[2]


@lru_cache
def get_settings() -> Settings:
    # Load .env from CWD and project root
    root = project_root()
    env_candidates = [Path.cwd() / ".env", root / ".env"]
    for env in env_candidates:
        if env.exists():
            from dotenv import load_dotenv

            load_dotenv(env, override=False)
            break
    return Settings()


def load_user_config(path: Path | None = None) -> UserConfig:
    settings = get_settings()
    cfg_path = path or settings.config_path
    if cfg_path.exists():
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            return UserConfig.model_validate(data)
        except Exception:
            return UserConfig()
    # Seed from env defaults
    return UserConfig(
        models=AgentModelConfig(
            brain=settings.brain_model,
            operator=settings.operator_model,
            marketer=settings.marketer_model,
            accountant=settings.accountant_model,
        ),
        budget_alert_usd=settings.autocorp_budget_alert_usd,
        require_human_approval=settings.autocorp_require_human_approval,
    )


def save_user_config(config: UserConfig, path: Path | None = None) -> Path:
    settings = get_settings()
    cfg_path = path or settings.config_path
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(
        json.dumps(config.model_dump(), indent=2),
        encoding="utf-8",
    )
    return cfg_path


def estimate_monthly_cost(
    models: AgentModelConfig,
    profile: str = "medium",
) -> dict[str, Any]:
    """Estimate monthly LLM spend for a usage profile across four agents."""
    usage = USAGE_PROFILES.get(profile, USAGE_PROFILES["medium"])
    # Split tokens across agents (Brain does most coding work)
    role_share = {
        "brain": 0.55,
        "operator": 0.15,
        "marketer": 0.15,
        "accountant": 0.15,
    }
    breakdown: dict[str, float] = {}
    total = 0.0
    for role, share in role_share.items():
        model_id = getattr(models, role)
        meta = MODEL_CATALOG.get(model_id, MODEL_CATALOG["gpt-4o"])
        inp = usage["input_tokens"] * share
        out = usage["output_tokens"] * share
        cost = (inp / 1_000_000) * meta["input_per_m"] + (out / 1_000_000) * meta["output_per_m"]
        breakdown[role] = round(cost, 2)
        total += cost
    return {
        "profile": profile,
        "profile_label": usage["label"],
        "companies_per_month": usage["companies"],
        "breakdown": breakdown,
        "total_usd": round(total, 2),
        "models": models.model_dump(),
    }


def resolve_model_for_role(role: AgentRoleName, user_config: UserConfig | None = None) -> str:
    cfg = user_config or load_user_config()
    return getattr(cfg.models, role)


def env_key_present(provider: str) -> bool:
    s = get_settings()
    mapping = {
        "anthropic": bool(s.anthropic_api_key),
        "openai": bool(s.openai_api_key),
        "openrouter": bool(s.openrouter_api_key),
        "deepseek": bool(s.deepseek_api_key),
        "ollama": True,  # local
    }
    return mapping.get(provider, False)


def get_available_models_for_role(role: AgentRoleName) -> list[tuple[str, dict[str, Any]]]:
    out = []
    for mid, meta in MODEL_CATALOG.items():
        if role in meta["roles"]:
            out.append((mid, meta))
    return out
