from __future__ import annotations

import dataclasses
import sqlite3
from collections.abc import Callable, Collection, Iterator, Sequence
from contextlib import contextmanager
from typing import Any, TypeVar, cast

from .connection import get_connection
from .dataclasses import Row, Video
from .tables import TABLES, check_fields, field_names, table_name

R = TypeVar("R", bound=Row)

# Per-column conversions from stored SQLite values; NULL always stays None.
_CONVERTERS: dict[type[Row], dict[str, Callable[[Any], Any]]] = {
    Video: {"own": bool},
}

_OPERATORS = {"=", "!=", "<", "<=", ">", ">=", "LIKE", "IN"}
_AGGREGATES = {"MIN", "MAX", "SUM", "COUNT"}

# (column, operator, value). "=" / "!=" with None become IS NULL / IS NOT NULL; an empty IN matches nothing.
Condition = tuple[str, str, object]


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


def _where(model: type[Row], where: Sequence[Condition]) -> tuple[str, list[object]]:
    """Build a WHERE clause from validated column conditions."""
    clauses: list[str] = []
    params: list[object] = []
    for column, operator, value in where:
        check_fields(model, (column,))
        if operator not in _OPERATORS:
            raise ValueError(f"unsupported operator {operator!r}")
        if operator == "IN":
            values = list(cast(Collection[object], value))
            if not values:
                clauses.append("0")
                continue
            clauses.append(f'"{column}" IN ({",".join("?" * len(values))})')
            params.extend(values)
        elif value is None and operator in ("=", "!="):
            clauses.append(f'"{column}" IS {"NOT " if operator == "!=" else ""}NULL')
        else:
            clauses.append(f'"{column}" {operator} ?')
            params.append(value)
    return (f" WHERE {' AND '.join(clauses)}" if clauses else ""), params


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
    where: Sequence[Condition] = (),
    order_by: Sequence[str] = (),
    limit: int | None = None,
    offset: int | None = None,
    distinct: bool = False,
    conn: sqlite3.Connection | None = None,
) -> list[R]:
    """Select only the requested columns of one table and return them as row instances."""
    names = field_names(model) if fields is None else tuple(fields)
    if not names:
        raise ValueError("fields must name at least one column")
    check_fields(model, names)
    where_sql, params = _where(model, where)
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
    return [_build(model, dict(row)) for row in rows]


def select_one(
    model: type[R],
    fields: Sequence[str] | None = None,
    *,
    where: Sequence[Condition] = (),
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
    where: Sequence[Condition] = (),
    conn: sqlite3.Connection | None = None,
) -> Any:
    """Return MIN/MAX/SUM/COUNT of one column over the matching rows."""
    if aggregate not in _AGGREGATES:
        raise ValueError(f"unsupported aggregate {aggregate!r}")
    check_fields(model, (column,))
    where_sql, params = _where(model, where)
    sql = f'SELECT {aggregate}("{column}") FROM {table_name(model)}{where_sql}'
    with connect(conn) as connection:
        return connection.execute(sql, params).fetchone()[0]


def fetch(model: type[R], query: Query, *, conn: sqlite3.Connection | None = None) -> list[R]:
    """Run a code-owned SELECT whose result columns are all fields of one row class."""
    with connect(conn) as connection:
        cursor = connection.execute(query.sql, query.params)
        names = [column[0] for column in cursor.description]
        check_fields(model, names)
        rows = cursor.fetchall()
    return [_build(model, dict(zip(names, row))) for row in rows]


def fetch_joined(
    query: Query,
    models: Sequence[type[Row]] = (),
    values: Sequence[str] = (),
    *,
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
    return results


def fetch_scalar(query: Query, *, conn: sqlite3.Connection | None = None) -> Any:
    """Run a code-owned SELECT and return the first column of its first row, or None."""
    with connect(conn) as connection:
        row = connection.execute(query.sql, query.params).fetchone()
    return row[0] if row else None
