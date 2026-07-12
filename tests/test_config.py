"""Config and cost estimate tests."""

from autocorp.core.config import (
    AgentModelConfig,
    estimate_monthly_cost,
)


def test_estimate_costs() -> None:
    models = AgentModelConfig(
        brain="claude-sonnet-4-5",
        operator="gpt-4o",
        marketer="gpt-4o",
        accountant="gpt-4o-mini",
    )
    light = estimate_monthly_cost(models, "light")
    heavy = estimate_monthly_cost(models, "heavy")
    assert light["total_usd"] > 0
    assert heavy["total_usd"] > light["total_usd"]
    assert "brain" in light["breakdown"]


def test_ollama_zero_cost() -> None:
    models = AgentModelConfig(
        brain="ollama/llama3.2",
        operator="ollama/mistral",
        marketer="ollama/mistral",
        accountant="ollama/mistral",
    )
    est = estimate_monthly_cost(models, "heavy")
    assert est["total_usd"] == 0.0
