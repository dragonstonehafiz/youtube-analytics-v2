from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from typing import TypeVar, overload

from . import reader
from .connection import get_connection
from .dataclasses import Row
from .filters import Predicate, where_clause
from .tables import GENERATED_KEYS, KEYS, NON_DECREASING, check_fields, field_names, table_name

R = TypeVar("R", bound=Row)


@overload
def write(row: R, *, conn: sqlite3.Connection | None = None) -> int: ...


@overload
def write(row: R, *, returning: Sequence[str], conn: sqlite3.Connection | None = None) -> R: ...


def write(row: R, *, returning: Sequence[str] | None = None, conn: sqlite3.Connection | None = None) -> int | R:
    """Upsert one row, leaving None fields untouched; return the count, or the `returning` fields as persisted."""
    if returning is None:
        return write_many([row], conn=conn)
    model = type(row)
    if not returning:
        raise ValueError("returning must name at least one field")
    check_fields(model, returning)
    with _transaction(conn) as connection:
        _, key = _write_one(connection, row)
        where = [(name, "=", value) for name, value in key.items()]
        stored = reader.select_one(model, returning, where=where, conn=connection)
    assert stored is not None
    return stored


def write_many(rows: Iterable[Row], *, conn: sqlite3.Connection | None = None) -> int:
    """Upsert rows of one class in order, atomically; return the number of rows processed."""
    batch = list(rows)
    if not batch:
        return 0
    model = type(batch[0])
    table_name(model)
    mixed = sorted({type(row).__name__ for row in batch if type(row) is not model})
    if mixed:
        raise ValueError(f"write_many() needs one row class; got {model.__name__} and {mixed}")
    with _transaction(conn) as connection:
        return sum(_write_one(connection, row)[0] for row in batch)


def update(row: Row, *, where: Sequence[Predicate], conn: sqlite3.Connection | None = None) -> int:
    """Set the row's non-None non-key fields on every row matching all predicates; never insert; return the count."""
    if not where:
        raise ValueError("update() needs at least one condition")
    model = type(row)
    where_sql, params = where_clause(model, where)
    values = _values(row)
    keyed = [key for key in KEYS[model] if key in values]
    if keyed:
        raise ValueError(f"update() cannot assign key fields {keyed}; match them in where")
    if not values:
        return 0
    assignments, assignment_params = _assignments(model, values)
    with _transaction(conn) as connection:
        cursor = connection.execute(
            f"UPDATE {table_name(model)} SET {assignments}{where_sql}", [*assignment_params, *params]
        )
        return cursor.rowcount


def delete(model: type[Row], *, where: Sequence[Predicate], conn: sqlite3.Connection | None = None) -> int:
    """Delete every row matching all predicates in one statement; return the direct count, excluding cascades."""
    if not where:
        raise ValueError("delete() needs at least one condition")
    where_sql, params = where_clause(model, where)
    with _transaction(conn) as connection:
        return connection.execute(f"DELETE FROM {table_name(model)}{where_sql}", params).rowcount


@contextmanager
def _transaction(conn: sqlite3.Connection | None) -> Iterator[sqlite3.Connection]:
    """Run writes in a new committed transaction, or in a savepoint inside a borrowed one."""
    if conn is not None:
        if not conn.in_transaction:
            raise ValueError("a borrowed connection must already be inside a transaction")
        conn.execute("SAVEPOINT writer")
        try:
            yield conn
        except BaseException:
            conn.execute("ROLLBACK TO writer")
            conn.execute("RELEASE writer")
            raise
        conn.execute("RELEASE writer")
        return

    owned = get_connection()
    try:
        # IMMEDIATE takes the write lock before the update-or-insert decision.
        owned.execute("BEGIN IMMEDIATE")
        try:
            yield owned
        except BaseException:
            owned.rollback()
            raise
        owned.commit()
    finally:
        owned.close()


def _values(row: Row) -> dict[str, object]:
    """Return the row's non-None fields by column name."""
    return {name: getattr(row, name) for name in field_names(type(row)) if getattr(row, name) is not None}


def _assignments(model: type[Row], updates: dict[str, object]) -> tuple[str, list[object]]:
    """Build SET assignments, raising non-decreasing columns only through MAX()."""
    non_decreasing = NON_DECREASING.get(model, frozenset())
    assignments = ", ".join(
        f'"{name}" = MAX("{name}", ?)' if name in non_decreasing else f'"{name}" = ?' for name in updates
    )
    return assignments, list(updates.values())


def _write_one(conn: sqlite3.Connection, row: Row) -> tuple[int, dict[str, object]]:
    """Update the row matching the key, or insert it when none matches; return the count and resolved key."""
    model = type(row)
    table = table_name(model)
    keys = KEYS[model]
    values = _values(row)

    missing = [key for key in keys if key not in values]
    if missing:
        if model in GENERATED_KEYS and len(missing) == len(keys):
            generated = _insert(conn, table, values)
            return 1, {keys[0]: generated}
        raise ValueError(f"{model.__name__} is missing key fields {missing}")

    key = {name: values[name] for name in keys}
    where = " AND ".join(f'"{name}" = ?' for name in keys)
    key_params = list(key.values())
    updates = {name: value for name, value in values.items() if name not in keys}
    if updates:
        assignments, params = _assignments(model, updates)
        cursor = conn.execute(f"UPDATE {table} SET {assignments} WHERE {where}", [*params, *key_params])
        if cursor.rowcount:
            return 1, key
    elif conn.execute(f"SELECT 1 FROM {table} WHERE {where}", key_params).fetchone():
        return 0, key
    _insert(conn, table, values)
    return 1, key


def _insert(conn: sqlite3.Connection, table: str, values: dict[str, object]) -> int | None:
    """Insert the given columns, omitted ones taking schema defaults; return the inserted rowid."""
    if not values:
        return conn.execute(f"INSERT INTO {table} DEFAULT VALUES").lastrowid
    columns = ", ".join(f'"{name}"' for name in values)
    placeholders = ", ".join("?" * len(values))
    return conn.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", list(values.values())).lastrowid
