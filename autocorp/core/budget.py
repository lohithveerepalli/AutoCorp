"""Budget system facade used by orchestration layer."""

from __future__ import annotations

from autocorp.db.brain import SharedBrain
from autocorp.tools.budget import BudgetToolkit


def get_budget_toolkit(brain: SharedBrain) -> BudgetToolkit:
    return BudgetToolkit(brain)
