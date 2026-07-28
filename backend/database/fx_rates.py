from __future__ import annotations

from .connection import _now, get_connection


def upsert_fx_rate(row: dict) -> None:
    """Insert or replace a daily USD/SGD exchange rate row."""
    row = {**row, "updated_at": _now()}
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO fx_rates (date, usd_to_sgd, updated_at)
            VALUES (:date, :usd_to_sgd, :updated_at)
            ON CONFLICT(date) DO UPDATE SET
                usd_to_sgd = excluded.usd_to_sgd,
                updated_at = excluded.updated_at
            """,
            row,
        )


def get_last_fx_rate() -> dict | None:
    """Return the most recent FX rate row {date, usd_to_sgd}, or None if table is empty."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT date, usd_to_sgd FROM fx_rates ORDER BY date DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def get_fx_rates(
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    """Return daily USD/SGD rates, ordered by date, with optional date filters."""
    conditions: list[str] = []
    params: list[object] = []
    if start_date:
        conditions.append("date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("date <= ?")
        params.append(end_date)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT date, usd_to_sgd FROM fx_rates {where} ORDER BY date",
            params,
        ).fetchall()
    return [dict(r) for r in rows]
