from __future__ import annotations

import dataclasses
import json
import sqlite3
import unittest
from unittest import mock

import database
from database import writer
from sync.write_preparation import related_video_rows
from database import (
    Comment,
    CommentAuthor,
    PlaylistItem,
    RelatedVideo,
    SyncRun,
    Video,
    VideoAnalytics,
    reader,
)
from database.dataclasses import Row
from database.reader import Query
from tests.support import (
    FIXED_NOW,
    IsolatedDatabaseTestCase,
    make_comment,
    make_comment_author,
    make_playlist,
    make_playlist_item,
    make_video,
    make_video_analytics,
)


class RegistryTest(IsolatedDatabaseTestCase):
    def test_every_application_table_is_registered_once(self) -> None:
        with database.get_connection() as conn:
            tables = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                )
            }
        self.assertEqual(len(reader.TABLES), 12)
        self.assertEqual(set(reader.TABLES.values()), tables)

    def test_dataclass_fields_match_schema_columns_in_order(self) -> None:
        with database.get_connection() as conn:
            for model, table in reader.TABLES.items():
                with self.subTest(table=table):
                    columns = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})")]
                    self.assertEqual(list(reader.field_names(model)), columns)

    def test_every_field_defaults_to_none(self) -> None:
        for model in reader.TABLES:
            with self.subTest(model=model.__name__):
                instance = model()
                self.assertTrue(all(value is None for value in dataclasses.asdict(instance).values()))

    def test_row_classes_carry_no_query_behavior(self) -> None:
        for model in reader.TABLES:
            with self.subTest(model=model.__name__):
                methods = {name for name in vars(model) if callable(getattr(model, name)) and not name.startswith("_")}
                self.assertEqual(methods, set())
                self.assertEqual(model.__mro__[1:], (Row, object))

    def test_unregistered_class_is_rejected(self) -> None:
        @dataclasses.dataclass
        class Stray(Row):
            id: str | None = None

        with self.assertRaises(ValueError):
            reader.select(Stray)


class ToDictTest(unittest.TestCase):
    def test_partial_construction_leaves_other_fields_none(self) -> None:
        video = Video(id="abc", title="Example")
        self.assertEqual(video.id, "abc")
        self.assertIsNone(video.published_at)

    def test_without_fields_returns_every_declared_field_including_none(self) -> None:
        result = Video(id="abc").to_dict()
        self.assertEqual(list(result), list(reader.field_names(Video)))
        self.assertIsNone(result["title"])

    def test_selected_fields_return_exactly_those_keys_including_none(self) -> None:
        self.assertEqual(Video(id="abc").to_dict(("id", "title")), {"id": "abc", "title": None})

    def test_prefix_renames_keys(self) -> None:
        author = CommentAuthor(display_name="Ann")
        self.assertEqual(author.to_dict(("display_name",), prefix="author_"), {"author_display_name": "Ann"})

    def test_unknown_field_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            Video(id="abc").to_dict(("id", "total_revenue_sgd"))

    def test_falsy_values_survive_and_encode(self) -> None:
        video = Video(id="abc", description="", view_count=0, own=False)
        result = video.to_dict(("description", "view_count", "own"))
        self.assertEqual(result, {"description": "", "view_count": 0, "own": False})
        self.assertEqual(json.loads(json.dumps(video.to_dict())), video.to_dict())


class ReaderTestCase(IsolatedDatabaseTestCase):
    def setUp(self) -> None:
        super().setUp()
        writer.write(make_video(
            "v-1", "Alpha", description="", view_count=0, published_at="2024-01-01T00:00:00Z",
        ))
        writer.write(make_video("v-2", "Beta 'quoted' \"title\"", published_at="2024-01-02T00:00:00Z"))
        writer.write(make_video("ext-1", "External", published_at="2024-01-03T00:00:00Z", own=False))
        with database.get_connection() as conn:
            conn.execute("UPDATE videos SET published_at = NULL WHERE id = 'ext-1'")

    def _traced(self) -> tuple[sqlite3.Connection, list[str]]:
        """Return a borrowed connection that records every SELECT it runs."""
        conn = database.get_connection()
        self.addCleanup(conn.close)
        statements: list[str] = []
        conn.set_trace_callback(lambda sql: statements.append(sql) if sql.lstrip().startswith("SELECT") else None)
        return conn, statements


class SelectTest(ReaderTestCase):
    def test_projection_selects_only_requested_columns_in_one_query(self) -> None:
        conn, statements = self._traced()
        videos = reader.select(Video, ("id", "title"), order_by=("id",), conn=conn)
        self.assertEqual(len(statements), 1)
        self.assertIn('SELECT "id", "title" FROM videos', statements[0])
        self.assertEqual([v.id for v in videos], ["ext-1", "v-1", "v-2"])
        self.assertIsNone(videos[0].published_at)

    def test_omitting_fields_selects_every_column(self) -> None:
        video = reader.select_one(Video, where=[("id", "=", "v-1")])
        assert video is not None
        self.assertEqual(video.title, "Alpha")
        self.assertIsNotNone(video.updated_at)

    def test_empty_field_list_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            reader.select(Video, ())

    def test_unknown_field_or_operator_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            reader.select(Video, ("id", "nope"))
        with self.assertRaises(ValueError):
            reader.select(Video, ("id",), where=[("nope", "=", 1)])
        with self.assertRaises(ValueError):
            reader.select(Video, ("id",), where=[("id", "; DROP", 1)])
        with self.assertRaises(ValueError):
            reader.select(Video, ("id",), order_by=("-nope",))

    def test_ownership_converts_to_bool_and_falsy_values_survive(self) -> None:
        videos = {v.id: v for v in reader.select(Video, ("id", "own", "description", "view_count"))}
        self.assertIs(videos["v-1"].own, True)
        self.assertIs(videos["ext-1"].own, False)
        self.assertEqual(videos["v-1"].description, "")
        self.assertEqual(videos["v-1"].view_count, 0)

    def test_values_with_quotes_are_bound_not_interpolated(self) -> None:
        video = reader.select_one(Video, ("id",), where=[("title", "=", "Beta 'quoted' \"title\"")])
        assert video is not None
        self.assertEqual(video.id, "v-2")
        self.assertEqual(reader.select(Video, ("id",), where=[("title", "LIKE", "%'%")])[0].id, "v-2")

    def test_none_equality_is_is_null(self) -> None:
        self.assertEqual([v.id for v in reader.select(Video, ("id",), where=[("published_at", "=", None)])], ["ext-1"])
        self.assertEqual(len(reader.select(Video, ("id",), where=[("published_at", "!=", None)])), 2)

    def test_in_matches_members_and_empty_in_matches_nothing(self) -> None:
        rows = reader.select(Video, ("id",), where=[("id", "IN", ["v-2", "missing", "v-1"])], order_by=("id",))
        self.assertEqual([v.id for v in rows], ["v-1", "v-2"])
        self.assertEqual(reader.select(Video, ("id",), where=[("id", "IN", [])]), [])

    def test_ordering_limit_and_offset(self) -> None:
        rows = reader.select(Video, ("id",), order_by=("-id",), limit=1, offset=1)
        self.assertEqual([v.id for v in rows], ["v-1"])
        rows = reader.select(Video, ("id",), order_by=("id",), offset=2)
        self.assertEqual([v.id for v in rows], ["v-2"])

    def test_select_one_returns_none_when_nothing_matches(self) -> None:
        self.assertIsNone(reader.select_one(Video, ("id",), where=[("id", "=", "missing")]))

    def test_composite_key_and_distinct(self) -> None:
        writer.write(make_video_analytics("v-1", "2024-01-05", views=3))
        writer.write(make_video_analytics("v-1", "2024-01-06", views=0))
        row = reader.select_one(VideoAnalytics, ("views",), where=[("video_id", "=", "v-1"), ("date", "=", "2024-01-06")])
        assert row is not None
        self.assertEqual(row.views, 0)
        ids = reader.select(VideoAnalytics, ("video_id",), distinct=True)
        self.assertEqual([r.video_id for r in ids], ["v-1"])

    def test_scalar_aggregates_and_empty_results(self) -> None:
        self.assertEqual(reader.scalar(Video, "MIN", "published_at", where=[("own", "=", True)]), "2024-01-01T00:00:00Z")
        self.assertEqual(reader.scalar(Video, "COUNT", "id"), 3)
        self.assertIsNone(reader.scalar(SyncRun, "MAX", "completed_at"))
        with self.assertRaises(ValueError):
            reader.scalar(Video, "GROUP_CONCAT", "id")


class ConnectionOwnershipTest(ReaderTestCase):
    def test_borrowed_connection_is_neither_committed_nor_closed(self) -> None:
        conn = database.get_connection()
        self.addCleanup(conn.close)
        conn.execute("INSERT INTO playlists (id, updated_at) VALUES ('p-uncommitted', 'now')")
        self.assertIsNotNone(reader.select_one(database.Playlist, ("id",), conn=conn))
        conn.rollback()
        self.assertIsNone(reader.select_one(database.Playlist, ("id",), conn=conn))

    def test_opened_connection_is_closed_after_the_read(self) -> None:
        opened: list[sqlite3.Connection] = []

        def tracking() -> sqlite3.Connection:
            conn = database.get_connection()
            opened.append(conn)
            return conn

        with mock.patch.object(reader, "get_connection", side_effect=tracking):
            reader.select(Video, ("id",))
        self.assertEqual(len(opened), 1)
        with self.assertRaises(sqlite3.ProgrammingError):
            opened[0].execute("SELECT 1")


class FetchTest(ReaderTestCase):
    def test_aliases_populate_one_row_class(self) -> None:
        rows = reader.fetch(Video, Query("SELECT v.id, v.title FROM videos v WHERE v.own = ? ORDER BY v.id", (1,)))
        self.assertEqual([(v.id, v.title) for v in rows], [("v-1", "Alpha"), ("v-2", "Beta 'quoted' \"title\"")])

    def test_grouped_aggregates_map_onto_fields(self) -> None:
        for day, views in (("2024-01-05", 4), ("2024-01-06", 6)):
            writer.write(make_video_analytics("v-1", day, views=views))
        conn, statements = self._traced()
        rows = reader.fetch(VideoAnalytics, Query(
            "SELECT va.video_id AS video_id, SUM(va.views) AS views FROM video_analytics va GROUP BY va.video_id"
        ), conn=conn)
        self.assertEqual(rows, [VideoAnalytics(video_id="v-1", views=10)])
        self.assertEqual(len(statements), 1)

    def test_unexpected_alias_is_reported(self) -> None:
        with self.assertRaises(ValueError) as raised:
            reader.fetch(Video, Query("SELECT v.id, 1 AS total_revenue_sgd FROM videos v"))
        self.assertIn("total_revenue_sgd", str(raised.exception))

    def test_empty_aggregate_scalar_is_none(self) -> None:
        self.assertIsNone(reader.fetch_scalar(Query("SELECT MAX(date) FROM video_analytics")))


class FetchJoinedTest(ReaderTestCase):
    def setUp(self) -> None:
        super().setUp()
        writer.write(make_comment_author("a-1", "Ann", youtube_channel_id="UC1"))
        writer.write(make_comment("c-1", "v-1", "a-1", like_count=0))
        writer.write(make_comment("c-2", "v-2", "a-1", like_count=5))

    def test_inner_join_splits_colliding_columns_into_components(self) -> None:
        query = Query(f"""
            SELECT {reader.joined_columns(Comment, 'c', ('id', 'like_count'))},
                {reader.joined_columns(CommentAuthor, 'ca', ('id', 'display_name'))},
                {reader.joined_columns(Video, 'v', ('id', 'title'))}
            FROM comments c
            JOIN comment_authors ca ON ca.id = c.author_id
            JOIN videos v ON v.id = c.video_id
            ORDER BY c.id
        """)
        conn, statements = self._traced()
        rows = reader.fetch_joined(query, (Comment, CommentAuthor, Video), conn=conn)
        self.assertEqual(len(statements), 1)
        self.assertEqual([r[Comment].id for r in rows], ["c-1", "c-2"])
        self.assertEqual(rows[0][Comment].like_count, 0)
        self.assertEqual(rows[0][CommentAuthor].id, "a-1")
        self.assertEqual(rows[1][Video].id, "v-2")
        self.assertIsNone(rows[0][Comment].text)
        self.assertEqual(rows[0].values, {})

    def test_left_join_with_missing_metadata_leaves_component_fields_none(self) -> None:
        writer.write_many(related_video_rows("v-1", "2024-01", [{"referrer_video_id": "unknown", "views": 2}], updated_at=FIXED_NOW))
        writer.write_many(related_video_rows("v-1", "2024-02", [{"referrer_video_id": "unknown", "views": 3}], updated_at=FIXED_NOW))
        writer.write_many(related_video_rows("v-1", "2024-01", [{"referrer_video_id": "ext-1", "views": 1}], updated_at=FIXED_NOW))
        query = Query(f"""
            SELECT rv.referrer_video_id AS related_videos__referrer_video_id,
                SUM(rv.views) AS related_videos__views,
                {reader.joined_columns(Video, 'ref', ('title', 'own'))},
                COUNT(*) AS month_count
            FROM related_videos rv
            LEFT JOIN videos ref ON ref.id = rv.referrer_video_id
            GROUP BY rv.referrer_video_id
            ORDER BY rv.referrer_video_id
        """)
        rows = reader.fetch_joined(query, (RelatedVideo, Video), ("month_count",))
        by_id = {r[RelatedVideo].referrer_video_id: r for r in rows}
        self.assertEqual(by_id["unknown"][RelatedVideo].views, 5)
        self.assertEqual(by_id["unknown"].values, {"month_count": 2})
        self.assertIsNone(by_id["unknown"][Video].title)
        self.assertIsNone(by_id["unknown"][Video].own)
        self.assertIs(by_id["ext-1"][Video].own, False)

    def test_unexpected_or_undeclared_columns_are_reported(self) -> None:
        with self.assertRaises(ValueError):
            reader.fetch_joined(Query("SELECT c.id AS comments__id, 1 AS extra FROM comments c"), (Comment,))
        with self.assertRaises(ValueError):
            reader.fetch_joined(Query("SELECT v.id AS videos__id FROM videos v"), (Comment,))
        with self.assertRaises(ValueError):
            reader.fetch_joined(Query("SELECT c.id AS comments__nope FROM comments c"), (Comment,))

    def test_components_serialize_to_flat_response_keys(self) -> None:
        writer.write(make_playlist("p-1"))
        writer.write(make_playlist_item("pi-1", "p-1", "v-1", 0))
        (row,) = reader.fetch_joined(Query(f"""
            SELECT {reader.joined_columns(PlaylistItem, 'pi', ('position',))},
                {reader.joined_columns(Video, 'v', ('id', 'description'))}
            FROM playlist_items pi JOIN videos v ON v.id = pi.video_id
        """), (PlaylistItem, Video))
        item = {**row[PlaylistItem].to_dict(("position",)), **row[Video].to_dict(("id", "description"))}
        self.assertEqual(item, {"position": 0, "id": "v-1", "description": ""})


if __name__ == "__main__":
    unittest.main()
