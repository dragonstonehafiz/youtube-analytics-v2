from __future__ import annotations

from dataclasses import dataclass

from .base import Row


@dataclass
class FxRate(Row):
    """One daily `fx_rates` row; unselected columns stay None."""

    date: str | None = None
    usd_to_sgd: float | None = None
    updated_at: str | None = None
