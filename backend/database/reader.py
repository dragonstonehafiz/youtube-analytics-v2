from __future__ import annotations

import dataclasses
import sqlite3
from collections.abc import Callable, Collection, Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import date, timedelta
from typing import Any, TypeVar, Union, cast

from .connection import get_connection
from .dataclasses import Row, Video
from .filters import Predicate, where_clause
from .tables import TABLES, check_fields, field_names, table_name

R = TypeVar("R", bound=Row)

# Per-column conversions from stored SQLite values; NULL always stays None.
_CONVERTERS: dict[type[Row], dict[str, Callable[[Any], Any]]] = {
    Video: {"own": bool},
}

_AGGREGATES = {"MIN", "MAX", "SUM", "COUNT"}


@dataclasses.dataclass(frozen=True)
class Query:
    """A code-owned, parameterized SELECT statement and its bound values."""

    sql: str
    params: tuple[object, ...] = ()


@dataclasses.dataclass
class Joined:
    """One joined result row: table components keyed by row class plus named computed values."""

    parts: dict[type[Row], Row]
    values: dict[str, Any]

    def __getitem__(self, model: type[R]) -> R:
        """Return the component row of the given class."""
        return cast(R, self.parts[model])


T = TypeVar("T", bound="Row | Joined")

# A result field: a column name on single-class results; on joined results, (row class, field) or a computed value name.
FieldRef = Union[str, tuple[type[Row], str]]


@dataclasses.dataclass(frozen=True)
class DateFill:
    """Fill missing days per identifier and breakdown up to its last observed day; fields are FieldRefs."""

    date: FieldRef
    metrics: Mapping[FieldRef, Any]
    start_date: str | None = None
    identifiers: Sequence[FieldRef] = ()
    breakdown: FieldRef | None = None
    # None fills the values observed per identifier, sorted; explicit values come first, then other observed ones.
    breakdown_values: Sequence[Any] | None = None
    # Copied into synthetic rows from the identifier's first observed row.
    constants: Sequence[FieldRef] = ()


def _value(result: Row | Joined, ref: FieldRef) -> Any:
    """Return one field of a row or joined result."""
    if isinstance(result, Joined):
        if isinstance(ref, str):
            return result.values[ref]
        model, name = ref
        return getattr(result.parts[model], name)
    return getattr(result, cast(str, ref))


def _check_fill(fill: DateFill, available: Collection[FieldRef]) -> None:
    """Raise when the fill references a field outside the result projection."""
    breakdown = [] if fill.breakdown is None else [fill.breakdown]
    references = [fill.date, *fill.identifiers, *breakdown, *fill.constants, *fill.metrics]
    unknown = [ref for ref in references if ref not in available]
    if unknown:
        raise ValueError(f"date fill references fields outside the result: {unknown}")


def _fill_dates(results: list[T], fill: DateFill, make: Callable[[dict[FieldRef, Any]], T]) -> list[T]:
    """Return results in identifier, date, breakdown order with default-metric rows for missing combinations."""
    series: dict[tuple[Any, ...], dict[tuple[str, Any], T]] = {}
    for result in results:
        identity = tuple(_value(result, ref) for ref in fill.identifiers)
        key = (_value(result, fill.date), None if fill.breakdown is None else _value(result, fill.breakdown))
        observed = series.setdefault(identity, {})
        if key in observed:
            raise ValueError(f"duplicate date-fill key {(*identity, *key)}")
        observed[key] = result

    filled: list[T] = []
    for identity, observed in series.items():
        days = [date.fromisoformat(day) for day, _ in observed]
        first = min(days) if fill.start_date is None else min(date.fromisoformat(fill.start_date), *days)
        last = max(days)
        seen = {value for _, value in observed}
        if fill.breakdown is None:
            breakdowns: list[Any] = [None]
        elif fill.breakdown_values is None:
            breakdowns = sorted(seen)
        else:
            breakdowns = [*fill.breakdown_values, *sorted(seen.difference(fill.breakdown_values))]
        template = {
            **{ref: _value(next(iter(observed.values())), ref) for ref in fill.constants},
            **dict(zip(fill.identifiers, identity)),
            **fill.metrics,
        }
        day = first
        while day <= last:
            text = day.isoformat()
            for value in breakdowns:
                found = observed.get((text, value))
                if found is None:
                    values = {**template, fill.date: text}
                    if fill.breakdown is not None:
                        values[fill.breakdown] = value
                    found = make(values)
                filled.append(found)
            day += timedelta(days=1)
    return filled


def _row_maker(model: type[R]) -> Callable[[dict[FieldRef, Any]], R]:
    """Return a builder of synthetic row instances from field values."""
    return lambda values: model(**cast(dict[str, Any], values))


def _joined_maker(models: Sequence[type[Row]], value_names: Sequence[str]) -> Callable[[dict[FieldRef, Any]], Joined]:
    """Return a builder of synthetic joined results; unset fields and computed values are None."""
    def make(values: dict[FieldRef, Any]) -> Joined:
        part_values: dict[type[Row], dict[str, Any]] = {model: {} for model in models}
        computed: dict[str, Any] = dict.fromkeys(value_names)
        for ref, value in values.items():
            if isinstance(ref, str):
                computed[ref] = value
            else:
                part_values[ref[0]][ref[1]] = value
        return Joined({model: model(**part) for model, part in part_values.items()}, computed)
    return make


def group_by(results: Sequence[T], field: FieldRef, *, limit: int | None = None) -> dict[Any, list[T]]:
    """Group ordered read results by one field's value, keeping the first `limit` per group in input order."""
    groups: dict[Any, list[T]] = {}
    for result in results:
        bucket = groups.setdefault(_value(result, field), [])
        if limit is None or len(bucket) < limit:
            bucket.append(result)
    return groups


def joined_columns(model: type[Row], alias: str, fields: Sequence[str] | None = None) -> str:
    """Return a SELECT list aliasing each column as `<table>__<field>` for fetch_joined()."""
    names = field_names(model) if fields is None else tuple(fields)
    check_fields(model, names)
    table = table_name(model)
    return ", ".join(f'{alias}."{name}" AS {table}__{name}' for name in names)


def _build(model: type[R], values: dict[str, Any]) -> R:
    """Construct a row instance, applying the registered column conversions."""
    converters = _CONVERTERS.get(model, {})
    for name, convert in converters.items():
        if values.get(name) is not None:
            values[name] = convert(values[name])
    return model(**values)


@contextmanager
def connect(conn: sqlite3.Connection | None = None) -> Iterator[sqlite3.Connection]:
    """Yield a borrowed connection untouched, or open one and close it afterwards."""
    if conn is not None:
        yield conn
        return
    owned = get_connection()
    try:
        yield owned
    finally:
        owned.close()


def _order(model: type[Row], order_by: Sequence[str]) -> str:
    """Build an ORDER BY clause from field names, where a leading '-' means descending."""
    terms = []
    for key in order_by:
        column = key.removeprefix("-")
        check_fields(model, (column,))
        terms.append(f'"{column}" {"DESC" if key.startswith("-") else "ASC"}')
    return f" ORDER BY {', '.join(terms)}" if terms else ""


def select(
    model: type[R],
    fields: Sequence[str] | None = None,
    *,
    where: Sequence[Predicate] = (),
    order_by: Sequence[str] = (),
    limit: int | None = None,
    offset: int | None = None,
    distinct: bool = False,
    fill_dates: DateFill | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[R]:
    """Select only the requested columns of one table and return them as row instances."""
    names = field_names(model) if fields is None else tuple(fields)
    if not names:
        raise ValueError("fields must name at least one column")
    check_fields(model, names)
    if fill_dates is not None:
        _check_fill(fill_dates, names)
    where_sql, params = where_clause(model, where)
    column_list = ", ".join(f'"{name}"' for name in names)
    sql = f"SELECT {'DISTINCT ' if distinct else ''}{column_list} FROM {table_name(model)}{where_sql}"
    sql += _order(model, order_by)
    if limit is not None or offset is not None:
        sql += " LIMIT ?"
        params.append(-1 if limit is None else limit)
    if offset is not None:
        sql += " OFFSET ?"
        params.append(offset)
    with connect(conn) as connection:
        rows = connection.execute(sql, params).fetchall()
    results = [_build(model, dict(row)) for row in rows]
    return results if fill_dates is None else _fill_dates(results, fill_dates, _row_maker(model))


def select_one(
    model: type[R],
    fields: Sequence[str] | None = None,
    *,
    where: Sequence[Predicate] = (),
    order_by: Sequence[str] = (),
    conn: sqlite3.Connection | None = None,
) -> R | None:
    """Return the first matching row instance, or None."""
    rows = select(model, fields, where=where, order_by=order_by, limit=1, conn=conn)
    return rows[0] if rows else None


def scalar(
    model: type[Row],
    aggregate: str,
    column: str,
    *,
    where: Sequence[Predicate] = (),
    conn: sqlite3.Connection | None = None,
) -> Any:
    """Return MIN/MAX/SUM/COUNT of one column over the matching rows."""
    if aggregate not in _AGGREGATES:
        raise ValueError(f"unsupported aggregate {aggregate!r}")
    check_fields(model, (column,))
    where_sql, params = where_clause(model, where)
    sql = f'SELECT {aggregate}("{column}") FROM {table_name(model)}{where_sql}'
    with connect(conn) as connection:
        return connection.execute(sql, params).fetchone()[0]


def fetch(
    model: type[R],
    query: Query,
    *,
    fill_dates: DateFill | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[R]:
    """Run a code-owned SELECT whose result columns are all fields of one row class."""
    with connect(conn) as connection:
        cursor = connection.execute(query.sql, query.params)
        names = [column[0] for column in cursor.description]
        check_fields(model, names)
        if fill_dates is not None:
            _check_fill(fill_dates, names)
        rows = cursor.fetchall()
    results = [_build(model, dict(zip(names, row))) for row in rows]
    return results if fill_dates is None else _fill_dates(results, fill_dates, _row_maker(model))


def fetch_joined(
    query: Query,
    models: Sequence[type[Row]] = (),
    values: Sequence[str] = (),
    *,
    fill_dates: DateFill | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[Joined]:
    """Run a code-owned SELECT, splitting `<table>__<field>` columns into rows and the rest into values."""
    by_table = {table_name(model): model for model in models}
    with connect(conn) as connection:
        cursor = connection.execute(query.sql, query.params)
        names = [column[0] for column in cursor.description]
        targets: list[tuple[type[Row] | None, str]] = []
        unexpected: list[str] = []
        for name in names:
            table, _, field = name.partition("__")
            model = by_table.get(table) if field else None
            if model is not None and field in field_names(model):
                targets.append((model, field))
            elif name in values:
                targets.append((None, name))
            else:
                unexpected.append(name)
        if unexpected:
            raise ValueError(f"unexpected result columns {unexpected}")
        if fill_dates is not None:
            _check_fill(fill_dates, [name if model is None else (model, name) for model, name in targets])
        rows = cursor.fetchall()

    results = []
    for row in rows:
        part_values: dict[type[Row], dict[str, Any]] = {model: {} for model in models}
        computed: dict[str, Any] = {}
        for (model, field), value in zip(targets, row):
            if model is None:
                computed[field] = value
            else:
                part_values[model][field] = value
        parts = {model: _build(model, part) for model, part in part_values.items()}
        results.append(Joined(parts, computed))
    if fill_dates is None:
        return results
    value_names = [name for model, name in targets if model is None]
    return _fill_dates(results, fill_dates, _joined_maker(models, value_names))


def fetch_scalar(query: Query, *, conn: sqlite3.Connection | None = None) -> Any:
    """Run a code-owned SELECT and return the first column of its first row, or None."""
    with connect(conn) as connection:
        row = connection.execute(query.sql, query.params).fetchone()
    return row[0] if row else None
