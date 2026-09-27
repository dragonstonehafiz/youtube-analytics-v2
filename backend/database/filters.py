from __future__ import annotations

import dataclasses
from collections.abc import Collection, Sequence
from typing import Union, cast

from .dataclasses import Row
from .tables import check_fields, table_name

_OPERATORS = {"=", "!=", "<", "<=", ">", ">=", "LIKE", "IN", "NOT IN"}

# (column, operator, value). "=" / "!=" with None become IS NULL / IS NOT NULL; an empty IN matches
# nothing and an empty NOT IN matches everything.
Condition = tuple[str, str, object]


@dataclasses.dataclass(frozen=True)
class NotExists:
    """Matches rows with no `model` row whose inner column equals the outer column for every (inner, outer) pair."""

    model: type[Row]
    correlations: tuple[tuple[str, str], ...]


Predicate = Union[Condition, NotExists]


def where_clause(model: type[Row], where: Sequence[Predicate]) -> tuple[str, list[object]]:
    """Build an AND-combined WHERE clause for one table from validated predicates, or "" when none."""
    table = table_name(model)
    clauses: list[str] = []
    params: list[object] = []
    for index, predicate in enumerate(where):
        if isinstance(predicate, NotExists):
            clauses.append(_not_exists(model, table, predicate, f"_inner{index}"))
            continue
        column, operator, value = predicate
        check_fields(model, (column,))
        if operator not in _OPERATORS:
            raise ValueError(f"unsupported operator {operator!r}")
        target = f'{table}."{column}"'
        if operator in ("IN", "NOT IN"):
            values = _members(operator, value)
            if not values:
                clauses.append("0" if operator == "IN" else "1")
                continue
            clauses.append(f'{target} {operator} ({",".join("?" * len(values))})')
            params.extend(values)
        elif value is None and operator in ("=", "!="):
            clauses.append(f'{target} IS {"NOT " if operator == "!=" else ""}NULL')
        else:
            clauses.append(f"{target} {operator} ?")
            params.append(value)
    return (f" WHERE {' AND '.join(clauses)}" if clauses else ""), params


def _members(operator: str, value: object) -> list[object]:
    """Return a membership collection's values, rejecting strings and NULLs inside NOT IN."""
    if isinstance(value, (str, bytes)):
        raise ValueError(f"{operator} needs a collection of values, not a string")
    values = list(cast(Collection[object], value))
    if operator == "NOT IN" and any(member is None for member in values):
        raise ValueError("NOT IN values cannot contain None")
    return values


def _not_exists(model: type[Row], table: str, predicate: NotExists, alias: str) -> str:
    """Build a correlated NOT EXISTS subquery against the outer table."""
    if not predicate.correlations:
        raise ValueError("NotExists needs at least one correlation")
    inner_table = table_name(predicate.model)
    check_fields(predicate.model, (inner for inner, _ in predicate.correlations))
    check_fields(model, (outer for _, outer in predicate.correlations))
    matches = " AND ".join(
        f'{alias}."{inner}" = {table}."{outer}"' for inner, outer in predicate.correlations
    )
    return f"NOT EXISTS (SELECT 1 FROM {inner_table} AS {alias} WHERE {matches})"
