from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager

from .connection import get_connection
from .dataclasses import Row
from .tables import GENERATED_KEYS, KEYS, NON_DECREASING, field_names, table_name


def write(row: Row, *, conn: sqlite3.Connection | None = None) -> int:
    """Upsert one row, leaving None fields untouched; return 1, or 0 for a key-only row that already exists."""
    return write_many([row], conn=conn)


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
        return sum(_write_one(connection, row) for row in batch)


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


def _write_one(conn: sqlite3.Connection, row: Row) -> int:
    """Update the row matching the key, or insert it when none matches."""
    model = type(row)
    table = table_name(model)
    keys = KEYS[model]
    values = {name: getattr(row, name) for name in field_names(model) if getattr(row, name) is not None}

    missing = [key for key in keys if key not in values]
    if missing:
        if model in GENERATED_KEYS and len(missing) == len(keys):
            return _insert(conn, table, values)
        raise ValueError(f"{model.__name__} is missing key fields {missing}")

    where = " AND ".join(f'"{key}" = ?' for key in keys)
    key_params = [values[key] for key in keys]
    updates = {name: value for name, value in values.items() if name not in keys}
    if updates:
        non_decreasing = NON_DECREASING.get(model, frozenset())
        assignments = ", ".join(
            f'"{name}" = MAX("{name}", ?)' if name in non_decreasing else f'"{name}" = ?' for name in updates
        )
        cursor = conn.execute(f"UPDATE {table} SET {assignments} WHERE {where}", [*updates.values(), *key_params])
        if cursor.rowcount:
            return 1
    elif conn.execute(f"SELECT 1 FROM {table} WHERE {where}", key_params).fetchone():
        return 0
    return _insert(conn, table, values)


def _insert(conn: sqlite3.Connection, table: str, values: dict[str, object]) -> int:
    """Insert the given columns; omitted columns take their schema defaults."""
    if not values:
        conn.execute(f"INSERT INTO {table} DEFAULT VALUES")
        return 1
    columns = ", ".join(f'"{name}"' for name in values)
    placeholders = ", ".join("?" * len(values))
    conn.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", list(values.values()))
    return 1
