"""Local preflight guard for paid presenter generation.

This guard is deliberately conservative: it does not purchase credits or attempt
to query/bypass a provider's quota. It only prevents a request when the local
project budget cannot cover the estimated presenter seconds.
"""

import math

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pipeline.models.entities import CostEntry, Project


def estimate_heygen_cost(duration_seconds: float, rate_per_minute: float = 4.0) -> float:
    """Estimate cost from seconds, rounded up to the provider's billing minute."""
    return math.ceil(max(0.0, duration_seconds) / 60.0) * rate_per_minute


def assert_project_budget(
    db: Session,
    project: Project,
    duration_seconds: float,
    *,
    rate_per_minute: float = 4.0,
) -> float:
    """Return the estimate or raise before a paid provider request starts."""
    estimate = estimate_heygen_cost(duration_seconds, rate_per_minute)
    spent = float(
        db.scalar(
            select(func.coalesce(func.sum(CostEntry.actual_cost_usd), 0.0)).where(
                CostEntry.project_id == project.id
            )
        )
        or 0.0
    )
    if spent + estimate > project.budget_usd:
        raise ValueError(
            f"HeyGen budget guard stopped this render: estimated ${estimate:.2f} "
            f"plus ${spent:.2f} already used exceeds the ${project.budget_usd:.2f} project budget."
        )
    return estimate
