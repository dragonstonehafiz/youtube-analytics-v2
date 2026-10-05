"""Allocated storage and row counts per application table, read through apsw for dbstat support."""

from __future__ import annotations

from typing import cast

import apsw

from ..connection import database_path
from ..tables import TABLES

_BUSY_TIMEOUT_MS = 30000


class StorageUnavailable(Exception):
    """The database storage could not be measured."""


def _integer(conn: apsw.Connection, sql: str) -> int:
    """Return the integer in the first column of a query's first row."""
    return cast(int, conn.execute(sql).fetchall()[0][0])


def database_storage() -> dict:
    """Total allocated bytes, per-table bytes (indexes included) and row counts, and unattributed bytes."""
    names = list(TABLES.values())
    try:
        conn = apsw.Connection(str(database_path()), flags=apsw.SQLITE_OPEN_READONLY)
        try:
            conn.set_busy_timeout(_BUSY_TIMEOUT_MS)
            # One read transaction so every figure comes from the same snapshot.
            conn.execute("BEGIN")
            page_size = _integer(conn, "PRAGMA page_size")
            page_count = _integer(conn, "PRAGMA page_count")
            owners = dict(conn.execute("SELECT name, tbl_name FROM sqlite_schema WHERE type IN ('table', 'index')"))
            sizes = dict.fromkeys(names, 0)
            for name, pgsize in conn.execute("SELECT name, pgsize FROM dbstat WHERE aggregate = TRUE"):
                owner = owners.get(name)
                if owner in sizes:
                    sizes[owner] += pgsize
            # Identifiers come only from the registered table set.
            counts = {name: _integer(conn, f'SELECT COUNT(*) FROM "{name}"') for name in names}
            conn.execute("COMMIT")
        finally:
            conn.close()
    except apsw.Error as exc:
        raise StorageUnavailable("database storage measurement failed") from exc

    total_bytes = page_size * page_count
    other_bytes = total_bytes - sum(sizes.values())
    if other_bytes < 0:
        raise StorageUnavailable("table storage exceeds the database total")
    return {
        "total_bytes": total_bytes,
        "other_bytes": other_bytes,
        "tables": [{"name": name, "size_bytes": sizes[name], "row_count": counts[name]} for name in names],
    }
