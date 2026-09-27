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
