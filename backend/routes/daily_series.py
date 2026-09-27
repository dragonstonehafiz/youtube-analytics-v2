from __future__ import annotations

from typing import Any

from database import VideoAnalytics, VideoTrafficSource, queries, reader

# Zero metrics for synthetic daily analytics rows read through fetch_joined().
ANALYTICS_METRIC_DEFAULTS: dict[reader.FieldRef, Any] = {
    **{(VideoAnalytics, name): 0 for name in queries.ANALYTICS_METRIC_FIELDS},
    **dict.fromkeys(queries.ANALYTICS_VALUES, 0),
}


def traffic_source_fill(start_date: str | None) -> reader.DateFill:
    """Fill each observed traffic-source type daily with zero views and watch time."""
    return reader.DateFill(
        date="date",
        breakdown="traffic_source_type",
        metrics={"views": 0, "watch_time_minutes": 0},
        start_date=start_date,
    )


def traffic_source_items(rows: list[VideoTrafficSource]) -> list[dict]:
    """Serialize daily traffic-source rows."""
    return [row.to_dict(queries.TRAFFIC_SOURCE_FIELDS) for row in rows]
