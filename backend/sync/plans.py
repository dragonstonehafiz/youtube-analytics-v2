from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

import database

# Canonical execution order for every sync stage. The backend — not the client — owns
# this order: a submitted plan always runs in this sequence regardless of the order its
# stages appear in the request. `pruning` sits between `videos` and `video_analytics` so
# it always runs after both discovery stages it depends on and before any stage whose
# rows would otherwise be cascade-deleted out from under it.
STAGE_ORDER: tuple[str, ...] = (
    "playlists",
    "videos",
    "pruning",
    "video_analytics",
    "video_traffic_sources",
    "fx_rates",
)

# Stages that delete data are never selected automatically; a plan built for unattended
# runs (e.g. the startup sync) must exclude them explicitly.
DESTRUCTIVE_STAGES: frozenset[str] = frozenset({"pruning"})

# The stages whose date range is configurable. Every other stage is always incremental
# and must not carry a scope or year.
PERIOD_AWARE_STAGES: frozenset[str] = frozenset({"video_analytics", "video_traffic_sources"})

# Stages that require both of these stages to run in the same plan, because they act on
# a discovery set only those stages populate.
STAGES_REQUIRING_PLAYLISTS_AND_VIDEOS: frozenset[str] = frozenset({"pruning"})

# Period scopes accepted for the period-aware stages.
SCOPES: tuple[str, ...] = ("incremental", "year", "all")

# The scope recorded in sync_runs for stages that are always incremental.
IMPLICIT_SCOPE = "incremental"

# A batch counts as a complete pipeline run only when every stage below succeeded under
# one batch_id. Derived from STAGE_ORDER so the two can never drift.
FULL_SYNC_TYPES: tuple[str, ...] = STAGE_ORDER


class PlanValidationError(ValueError):
    """Raised when a sync plan is semantically invalid and must not be executed."""


@dataclass(frozen=True)
class PlanStage:
    """One stage of a sync plan.

    `scope` and `year` are set only for the period-aware stages; they stay None for
    stages that are always incremental, which keeps validation idempotent — a validated
    plan can be revalidated without being rejected for carrying a scope it should not.
    """

    stage: str
    scope: str | None = None
    year: int | None = None


def available_years() -> tuple[int, ...]:
    """Return the selectable analytics years, newest first.

    Spans the earliest published year through the current year. Empty when no videos
    have been synced yet, in which case no year-scoped plan can be validated.
    """
    earliest = database.get_earliest_published_year()
    current_year = date.today().year
    if earliest is None or earliest > current_year:
        return ()
    return tuple(range(current_year, earliest - 1, -1))


def recorded_scope(stage: PlanStage) -> str:
    """Return the scope to record in sync_runs for a validated stage."""
    if stage.stage in PERIOD_AWARE_STAGES and stage.scope is not None:
        return stage.scope
    return IMPLICIT_SCOPE


def recorded_year(stage: PlanStage) -> int | None:
    """Return the year to record in sync_runs for a validated stage."""
    return stage.year if stage.stage in PERIOD_AWARE_STAGES else None


def validate_plan(stages: Sequence[PlanStage]) -> tuple[PlanStage, ...]:
    """Validate a sync plan and return its stages in canonical execution order.

    Raises PlanValidationError when the plan is empty, repeats a stage, names an unknown
    stage, omits or misuses a period, or requests an unavailable year. Idempotent: the
    returned tuple revalidates cleanly.
    """
    if not stages:
        raise PlanValidationError("At least one stage must be selected")

    seen: set[str] = set()
    for stage in stages:
        if stage.stage not in STAGE_ORDER:
            raise PlanValidationError(f"Unknown stage: {stage.stage}")
        if stage.stage in seen:
            raise PlanValidationError(f"Stage listed more than once: {stage.stage}")
        seen.add(stage.stage)

        if stage.stage in PERIOD_AWARE_STAGES:
            _validate_period(stage)
        elif stage.scope is not None or stage.year is not None:
            raise PlanValidationError(f"{stage.stage} does not accept a scope or year")

    for name in STAGES_REQUIRING_PLAYLISTS_AND_VIDEOS & seen:
        missing = {"playlists", "videos"} - seen
        if missing:
            raise PlanValidationError(
                f"{name} requires {' and '.join(sorted(missing))} in the same plan"
            )

    by_stage = {stage.stage: stage for stage in stages}
    return tuple(by_stage[name] for name in STAGE_ORDER if name in by_stage)


def _validate_period(stage: PlanStage) -> None:
    """Validate the scope/year pair of one period-aware stage."""
    if stage.scope is None:
        raise PlanValidationError(f"{stage.stage} requires a scope")
    if stage.scope not in SCOPES:
        raise PlanValidationError(f"scope must be one of: {', '.join(SCOPES)}")

    if stage.scope == "year":
        if stage.year is None:
            raise PlanValidationError(f"{stage.stage} requires a year when scope=year")
        years = available_years()
        if not years:
            raise PlanValidationError("No analytics years are available yet")
        if stage.year not in years:
            raise PlanValidationError(
                f"year must be between {years[-1]} and {years[0]}"
            )
    elif stage.year is not None:
        raise PlanValidationError(f"year is only allowed when scope=year, not scope={stage.scope}")


def full_incremental_plan() -> tuple[PlanStage, ...]:
    """Return the non-destructive startup plan: every stage except pruning.

    Pruning deletes videos and is opt-in only — never selected automatically, so a
    truncated or unattended run can never remove data.
    """
    return tuple(
        PlanStage(name, IMPLICIT_SCOPE if name in PERIOD_AWARE_STAGES else None)
        for name in STAGE_ORDER
        if name not in DESTRUCTIVE_STAGES
    )
