"""Legacy/New video statistics for the channel or a video-ID scope."""

from __future__ import annotations

from collections.abc import Collection

from .. import reader
from ..reader import Query

_CATALOG_VALUES = (
    "legacy_video_count", "legacy_short_count", "new_video_count", "new_short_count",
    "total_comments", "video_comments", "short_comments",
    "total_public", "total_private", "total_unlisted",
)
_PERIOD_VALUES = ("bucket", "content_type", "period_views", "period_revenue_sgd")


def _empty_video_stats() -> dict:
    """Return a zeroed-out video stats dict matching the get_video_stats() contract."""
    return {
        "legacy_video_count": 0, "legacy_video_views": 0, "legacy_video_earnings_sgd": 0.0,
        "legacy_short_count": 0, "legacy_short_views": 0, "legacy_short_earnings_sgd": 0.0,
        "new_video_count": 0, "new_video_views": 0, "new_video_earnings_sgd": 0.0,
        "new_short_count": 0, "new_short_views": 0, "new_short_earnings_sgd": 0.0,
        "total_comments": 0, "video_comments": 0, "short_comments": 0,
        "total_public": 0, "total_private": 0, "total_unlisted": 0,
    }


def get_video_stats(
    title: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    content_type: str | None = None,
    privacy_status: str | None = None,
    video_ids: Collection[str] | None = None,
) -> dict:
    """Return filtered video statistics split into Legacy and New groups; None scopes to the whole channel."""
    scoped_ids = None if video_ids is None else list(dict.fromkeys(video_ids))
    if scoped_ids is not None and not scoped_ids:
        return _empty_video_stats()

    scope_conditions: list[str] = ["v.own = 1"]
    scope_params: list[object] = []
    if scoped_ids:
        scope_conditions.append(f"v.id IN ({','.join('?' * len(scoped_ids))})")
        scope_params.extend(scoped_ids)

    conditions: list[str] = list(scope_conditions)
    params: list[object] = list(scope_params)
    if title:
        conditions.append("(v.title LIKE ? OR v.id LIKE ?)")
        params.append(f"%{title}%")
        params.append(f"%{title}%")
    if content_type:
        conditions.append("v.content_type = ?")
        params.append(content_type)
    if privacy_status:
        conditions.append("v.privacy_status = ?")
        params.append(privacy_status)
    where = f"WHERE {' AND '.join(conditions)}"

    with reader.connect() as conn:
        (analytics,) = reader.fetch_joined(
            Query(
                f"""
                SELECT MIN(va.date) AS min_value, MAX(va.date) AS max_value FROM video_analytics va
                JOIN videos v ON v.id = va.video_id
                WHERE {' AND '.join(scope_conditions)}
                """,
                tuple(scope_params),
            ),
            values=("min_value", "max_value"),
            conn=conn,
        )
        (publication,) = reader.fetch_joined(
            Query(f"SELECT MIN(v.published_at) AS min_value, MAX(v.published_at) AS max_value FROM videos v {where}", tuple(params)),
            values=("min_value", "max_value"),
            conn=conn,
        )
        publication_min = publication.values["min_value"]
        publication_max = publication.values["max_value"]

        eff_start = start_date or analytics.values["min_value"] or (publication_min[:10] if publication_min else None)
        eff_end = end_date or analytics.values["max_value"] or (publication_max[:10] if publication_max else None)
        eff_end_ts = f"{eff_end}T23:59:59" if eff_end else None

        (catalog,) = reader.fetch_joined(
            Query(
                f"""
                SELECT
                    COALESCE(SUM(CASE WHEN v.published_at IS NOT NULL AND v.published_at < ? AND v.content_type = 'video' THEN 1 ELSE 0 END), 0) AS legacy_video_count,
                    COALESCE(SUM(CASE WHEN v.published_at IS NOT NULL AND v.published_at < ? AND v.content_type = 'short' THEN 1 ELSE 0 END), 0) AS legacy_short_count,
                    COALESCE(SUM(CASE WHEN v.published_at IS NOT NULL AND v.published_at >= ? AND v.published_at <= ? AND v.content_type = 'video' THEN 1 ELSE 0 END), 0) AS new_video_count,
                    COALESCE(SUM(CASE WHEN v.published_at IS NOT NULL AND v.published_at >= ? AND v.published_at <= ? AND v.content_type = 'short' THEN 1 ELSE 0 END), 0) AS new_short_count,
                    COALESCE(SUM(v.comment_count), 0) AS total_comments,
                    COALESCE(SUM(CASE WHEN v.content_type = 'video' THEN v.comment_count ELSE 0 END), 0) AS video_comments,
                    COALESCE(SUM(CASE WHEN v.content_type = 'short' THEN v.comment_count ELSE 0 END), 0) AS short_comments,
                    COALESCE(SUM(CASE WHEN v.privacy_status = 'public' THEN 1 ELSE 0 END), 0) AS total_public,
                    COALESCE(SUM(CASE WHEN v.privacy_status = 'private' THEN 1 ELSE 0 END), 0) AS total_private,
                    COALESCE(SUM(CASE WHEN v.privacy_status = 'unlisted' THEN 1 ELSE 0 END), 0) AS total_unlisted
                FROM videos v
                {where}
                """,
                (eff_start, eff_start, eff_start, eff_end_ts, eff_start, eff_end_ts, *params),
            ),
            values=_CATALOG_VALUES,
            conn=conn,
        )

        period_rows = reader.fetch_joined(
            Query(
                f"""
                SELECT
                    CASE
                        WHEN v.published_at IS NULL THEN NULL
                        WHEN v.published_at < ? THEN 'legacy'
                        WHEN v.published_at >= ? AND v.published_at <= ? THEN 'new'
                        ELSE NULL
                    END AS bucket,
                    v.content_type AS content_type,
                    COALESCE(SUM(pa.period_views), 0) AS period_views,
                    COALESCE(SUM(pa.period_revenue_sgd), 0) AS period_revenue_sgd
                FROM videos v
                JOIN (
                    SELECT va.video_id AS video_id,
                        SUM(va.views) AS period_views,
                        SUM(va.estimated_revenue * fx.usd_to_sgd) AS period_revenue_sgd
                    FROM video_analytics va
                    LEFT JOIN fx_rates fx ON fx.date = va.date
                    WHERE va.date >= ? AND va.date <= ?
                    GROUP BY va.video_id
                ) pa ON pa.video_id = v.id
                {where}
                GROUP BY bucket, v.content_type
                """,
                (eff_start, eff_start, eff_end_ts, eff_start, eff_end, *params),
            ),
            values=_PERIOD_VALUES,
            conn=conn,
        )

    result = {**_empty_video_stats(), **catalog.values}
    for period_row in period_rows:
        bucket = period_row.values["bucket"]
        if bucket is None or period_row.values["content_type"] not in ("video", "short"):
            continue
        prefix = f"{bucket}_{period_row.values['content_type']}"
        result[f"{prefix}_views"] = period_row.values["period_views"] or 0
        result[f"{prefix}_earnings_sgd"] = period_row.values["period_revenue_sgd"] or 0.0
    return result
