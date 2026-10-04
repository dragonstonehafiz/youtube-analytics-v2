from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest import mock

import database
from database import VideoAnalytics, reader, writer
from tests.support import (
    IsolatedDatabaseTestCase,
    make_fx_rate,
    make_playlist,
    make_playlist_item,
    make_video,
    make_video_analytics,
)

_MIGRATION_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "lifetime-earnings-migration.py"
_spec = importlib.util.spec_from_file_location("lifetime_earnings_migration", _MIGRATION_SCRIPT)
assert _spec is not None and _spec.loader is not None
_migration_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration_module)
migrate = _migration_module.migrate


def _columns(table: str) -> set[str]:
    """Return a table's column names."""
    with database.get_connection() as conn:
        return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def _totals() -> dict[str, float]:
    """Return every stored video and playlist total by ID."""
    with database.get_connection() as conn:
        videos = conn.execute("SELECT id, total_revenue_sgd FROM videos").fetchall()
        playlists = conn.execute("SELECT id, total_earnings_sgd FROM playlists").fetchall()
    return {**{row[0]: row[1] for row in videos}, **{row[0]: row[1] for row in playlists}}


class LifetimeEarningsMigrationTest(IsolatedDatabaseTestCase):
    def setUp(self) -> None:
        super().setUp()
        writer.write_many([make_video("v-1"), make_video("v-2"), make_video("v-ext", own=False)])
        writer.write(make_fx_rate("2024-01-01", 2.0))
        writer.write_many([
            make_video_analytics("v-1", "2024-01-01", estimated_revenue=5.0),
            make_video_analytics("v-2", "2024-01-01", estimated_revenue=1.0),
        ])
        writer.write(make_playlist("p-1"))
        writer.write_many([
            make_playlist_item("pi-1", "p-1", "v-1", 0),
            make_playlist_item("pi-2", "p-1", "v-1", 1),
            make_playlist_item("pi-3", "p-1", "v-2", 2),
            make_playlist_item("pi-4", "p-1", "v-ext", 3),
        ])

    def _drop_columns(self) -> None:
        """Turn the test database into one created before the earnings columns existed."""
        with database.get_connection() as conn:
            conn.execute("ALTER TABLE videos DROP COLUMN total_revenue_sgd")
            conn.execute("ALTER TABLE playlists DROP COLUMN total_earnings_sgd")

    def test_adds_missing_columns_and_fills_totals(self) -> None:
        self._drop_columns()

        result = migrate()

        self.assertEqual(result.columns_added, ["videos.total_revenue_sgd", "playlists.total_earnings_sgd"])
        self.assertEqual((result.videos, result.playlists), (2, 1))
        self.assertEqual(_totals(), {"v-1": 10.0, "v-2": 2.0, "v-ext": 0.0, "p-1": 12.0})

    def test_a_current_database_gains_no_columns_and_reruns_recalculate(self) -> None:
        self.assertEqual(migrate().columns_added, [])
        writer.write(make_video_analytics("v-1", "2024-01-01", estimated_revenue=3.0))

        migrate()

        self.assertEqual(_totals(), {"v-1": 6.0, "v-2": 2.0, "v-ext": 0.0, "p-1": 8.0})

    def test_analytics_rows_are_unchanged(self) -> None:
        self._drop_columns()

        migrate()

        rows = reader.select(VideoAnalytics, ("video_id", "estimated_revenue"), order_by=("video_id",))
        self.assertEqual([(row.video_id, row.estimated_revenue) for row in rows], [("v-1", 5.0), ("v-2", 1.0)])

    def test_a_failure_rolls_back_the_added_columns(self) -> None:
        self._drop_columns()

        with mock.patch.object(_migration_module.catalog, "lifetime_earnings", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                migrate()

        self.assertNotIn("total_revenue_sgd", _columns("videos"))
        self.assertNotIn("total_earnings_sgd", _columns("playlists"))
