"""Daily analytics series and top-video rankings for owned videos."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from typing import Any

from .. import reader
from ..dataclasses import Video, VideoAnalytics
from ..reader import Query, joined_columns
from ._conditions import date_bounds, video_conditions

_DEFAULT_CONTENT_TYPES = ("video", "short")

_METRIC_FIELDS = (
    "views",
    "watch_time_minutes",
    "estimated_revenue",
    "average_view_duration_seconds",
    "average_view_percentage",
    "likes",
    "subscribers_gained",
    "subscribers_lost",
)
_REVENUE_SGD = "estimated_revenue_sgd"
_METRIC_DEFAULTS: dict[reader.FieldRef, Any] = {
    **{(VideoAnalytics, name): 0 for name in _METRIC_FIELDS},
    _REVENUE_SGD: 0,
}

_TOP_VIDEO_FIELDS = ("id", "title", "published_at", "thumbnail_url", "content_type")
_TOP_VIDEO_VALUES = ("period_views", "period_earnings_sgd", "period_watch_time_hours")
_TOP_VIDEO_ORDER_BY = {
    "views": "period_views DESC, v.id ASC",
    "watch_time": "period_watch_time_hours DESC, period_views DESC, v.id ASC",
}


def daily_analytics(
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    content_type: str | None = None,
    privacy_status: str | None = None,
    title: str | None = None,
    video_ids: Collection[str] | None = None,
    fill_content_types: Sequence[str] | None = _DEFAULT_CONTENT_TYPES,
) -> list[dict]:
    """Owned-video metrics summed (durations averaged) per date and content type, zero-filled daily."""
    conditions, params = video_conditions(
        video_ids=video_ids, title=title, content_type=content_type, privacy_status=privacy_status
    )
    date_conditions, date_params = date_bounds("va.date", start_date, end_date)
    query = Query(
        f"""
        SELECT va.date AS video_analytics__date,
            v.content_type AS videos__content_type,
            SUM(va.views) AS video_analytics__views,
            SUM(va.watch_time_minutes) AS video_analytics__watch_time_minutes,
            SUM(va.estimated_revenue) AS video_analytics__estimated_revenue,
            COALESCE(SUM(va.estimated_revenue * fx.usd_to_sgd), 0) AS {_REVENUE_SGD},
            AVG(va.average_view_duration_seconds) AS video_analytics__average_view_duration_seconds,
            AVG(va.average_view_percentage) AS video_analytics__average_view_percentage,
            SUM(va.likes) AS video_analytics__likes,
            SUM(va.subscribers_gained) AS video_analytics__subscribers_gained,
            SUM(va.subscribers_lost) AS video_analytics__subscribers_lost
        FROM video_analytics va
        JOIN videos v ON v.id = va.video_id
        LEFT JOIN fx_rates fx ON fx.date = va.date
        WHERE {' AND '.join([*conditions, *date_conditions])}
        GROUP BY va.date, v.content_type
        ORDER BY va.date, v.content_type
        """,
        (*params, *date_params),
    )
    # A content_type filter narrows the filled types to it; None fills only the observed types.
    if fill_content_types is None:
        breakdown_values = None
    else:
        breakdown_values = [content_type] if content_type else list(fill_content_types)
    fill = reader.DateFill(
        date=(VideoAnalytics, "date"),
        breakdown=(Video, "content_type"),
        breakdown_values=breakdown_values,
        metrics=_METRIC_DEFAULTS,
        start_date=start_date,
    )
    rows = reader.fetch_joined(query, (VideoAnalytics, Video), (_REVENUE_SGD,), fill_dates=fill)
    return [
        {
            **row[VideoAnalytics].to_dict(("date",)),
            **row[Video].to_dict(("content_type",)),
            **row[VideoAnalytics].to_dict(_METRIC_FIELDS),
            **row.values,
        }
        for row in rows
    ]


def top_videos(
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    content_type: str | None = None,
    privacy_status: str | None = None,
    title: str | None = None,
    sort_by: str = "views",
    limit: int = 10,
    video_ids: Collection[str] | None = None,
) -> list[dict]:
    """Owned videos ranked by period views or watch time, with period earnings in SGD."""
    conditions, params = video_conditions(
        video_ids=video_ids, title=title, content_type=content_type, privacy_status=privacy_status
    )
    date_conditions, date_params = date_bounds("va.date", start_date, end_date)
    order_by = _TOP_VIDEO_ORDER_BY.get(sort_by, _TOP_VIDEO_ORDER_BY["views"])
    query = Query(
        f"""
        SELECT {joined_columns(Video, 'v', _TOP_VIDEO_FIELDS)},
            SUM(va.views) AS period_views,
            COALESCE(SUM(va.estimated_revenue * fx.usd_to_sgd), 0) AS period_earnings_sgd,
            COALESCE(SUM(va.watch_time_minutes), 0) / 60.0 AS period_watch_time_hours
        FROM video_analytics va
        JOIN videos v ON v.id = va.video_id
        LEFT JOIN fx_rates fx ON fx.date = va.date
        WHERE {' AND '.join([*conditions, *date_conditions])}
        GROUP BY v.id
        ORDER BY {order_by}
        LIMIT ?
        """,
        (*params, *date_params, limit),
    )
    rows = reader.fetch_joined(query, (Video,), _TOP_VIDEO_VALUES)
    return [{**row[Video].to_dict(_TOP_VIDEO_FIELDS), **row.values} for row in rows]
