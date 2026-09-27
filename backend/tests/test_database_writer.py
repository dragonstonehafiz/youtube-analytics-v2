from __future__ import annotations

import sqlite3
import threading
import unittest
from collections.abc import Iterator
from unittest import mock

import database
from database import (
    Comment,
    CommentAuthor,
    FxRate,
    RelatedVideo,
    SearchTerm,
    SyncCoverage,
    SyncRun,
    Video,
    VideoAnalytics,
    VideoTrafficSource,
    reader,
    tables,
    writer,
)
from tests.support import (
    FIXED_NOW,
    IsolatedDatabaseTestCase,
    make_comment,
    make_comment_author,
    make_video,
    make_video_analytics,
)


def _stored(sql: str, *params: object) -> list[sqlite3.Row]:
    """Return rows from a raw read on a fresh connection."""
    with database.get_connection() as conn:
        return conn.execute(sql, params).fetchall()


class FromDictTest(unittest.TestCase):
    def test_every_model_round_trips_through_to_dict(self) -> None:
        for model in tables.TABLES:
            with self.subTest(model=model.__name__):
                values = {name: f"value-{name}" for name in tables.field_names(model)}
                self.assertEqual(model.from_dict(values).to_dict(), values)

    def test_absent_fields_are_none_and_supplied_falsy_values_are_kept(self) -> None:
        video = Video.from_dict({"id": "v-1", "description": "", "view_count": 0, "own": False, "title": None})
        self.assertIsInstance(video, Video)
        self.assertEqual((video.description, video.view_count, video.own), ("", 0, False))
        self.assertIsNone(video.title)
        self.assertIsNone(video.published_at)

    def test_unknown_keys_are_rejected(self) -> None:
        with self.assertRaises(ValueError) as raised:
            Video.from_dict({"id": "v-1", "total_revenue_sgd": 1.0})
        self.assertIn("total_revenue_sgd", str(raised.exception))

    def test_the_source_mapping_is_not_mutated(self) -> None:
        source = {"id": "v-1", "title": "Alpha"}
        Video.from_dict(source)
        self.assertEqual(source, {"id": "v-1", "title": "Alpha"})


class RegistryKeysTest(IsolatedDatabaseTestCase):
    def test_keys_match_each_table_primary_key(self) -> None:
        with database.get_connection() as conn:
            for model, table in tables.TABLES.items():
                with self.subTest(table=table):
                    columns = conn.execute(f"PRAGMA table_info({table})").fetchall()
                    primary = [row["name"] for row in sorted(columns, key=lambda row: row["pk"]) if row["pk"]]
                    self.assertEqual(list(tables.KEYS[model]), primary)

    def test_reader_uses_the_shared_registry(self) -> None:
        self.assertIs(reader.TABLES, tables.TABLES)


class WriteTest(IsolatedDatabaseTestCase):
    def test_inserts_a_new_row_and_returns_one(self) -> None:
        self.assertEqual(writer.write(make_video("v-1", "Alpha")), 1)
        (row,) = _stored("SELECT title, own, updated_at FROM videos WHERE id = 'v-1'")
        self.assertEqual((row["title"], row["own"], row["updated_at"]), ("Alpha", 1, FIXED_NOW))

    def test_repeated_write_updates_the_row_and_still_returns_one(self) -> None:
        writer.write(make_video("v-1", "Alpha", view_count=1))
        self.assertEqual(writer.write(make_video("v-1", "Alpha", view_count=1)), 1)
        writer.write(make_video("v-1", "Beta", view_count=2, updated_at="2024-07-01T00:00:00+00:00"))
        (row,) = _stored("SELECT title, view_count, updated_at FROM videos WHERE id = 'v-1'")
        self.assertEqual((row["title"], row["view_count"], row["updated_at"]), ("Beta", 2, "2024-07-01T00:00:00+00:00"))
        self.assertEqual(len(_stored("SELECT id FROM videos")), 1)

    def test_none_fields_keep_the_stored_value(self) -> None:
        writer.write(make_video("v-1", "Alpha", description="Kept", content_type="short"))
        writer.write(Video(id="v-1", view_count=5, description=None, content_type=None))
        (row,) = _stored("SELECT title, description, content_type, view_count FROM videos WHERE id = 'v-1'")
        self.assertEqual(tuple(row), ("Alpha", "Kept", "short", 5))

    def test_falsy_values_are_written(self) -> None:
        writer.write(make_video("v-1", "Alpha", description="Text", view_count=9, own=True))
        writer.write(Video(id="v-1", description="", view_count=0))
        writer.write(make_comment_author("a-1", "Ann", youtube_channel_id="UC1"))
        writer.write(make_comment("c-1", "v-1", "a-1", like_count=4))
        writer.write(Comment(id="c-1", like_count=0))
        (video,) = _stored("SELECT description, view_count FROM videos WHERE id = 'v-1'")
        (comment,) = _stored("SELECT like_count FROM comments WHERE id = 'c-1'")
        self.assertEqual((video["description"], video["view_count"], comment["like_count"]), ("", 0, 0))

    def test_a_partial_row_updates_an_existing_row_without_its_required_fields(self) -> None:
        writer.write(make_video("v-1", "Alpha"))
        self.assertEqual(writer.write(Video(id="v-1", view_count=7)), 1)
        (row,) = _stored("SELECT title, view_count FROM videos WHERE id = 'v-1'")
        self.assertEqual((row["title"], row["view_count"]), ("Alpha", 7))

    def test_a_new_row_missing_a_required_field_fails_and_writes_nothing(self) -> None:
        with self.assertRaises(sqlite3.IntegrityError):
            writer.write(Video(id="v-new", view_count=1))
        self.assertEqual(_stored("SELECT id FROM videos"), [])

    def test_omitted_columns_take_schema_defaults_on_insert(self) -> None:
        writer.write(Video(id="v-1", title="Alpha", updated_at=FIXED_NOW))
        writer.write(make_comment_author("a-1", "Ann"))
        writer.write(Comment(
            id="c-1", thread_id="t-1", video_id="v-1", author_id="a-1", text="hi",
            published_at=FIXED_NOW, youtube_updated_at=FIXED_NOW, updated_at=FIXED_NOW,
        ))
        (video,) = _stored("SELECT own, description FROM videos WHERE id = 'v-1'")
        (comment,) = _stored("SELECT like_count, total_reply_count FROM comments WHERE id = 'c-1'")
        self.assertEqual((video["own"], video["description"]), (1, None))
        self.assertEqual(tuple(comment), (0, 0))

    def test_composite_keys_match_on_every_key_column(self) -> None:
        writer.write(make_video("v-1", "Alpha"))
        writer.write(make_video_analytics("v-1", "2024-01-01", views=1))
        writer.write(make_video_analytics("v-1", "2024-01-02", views=2))
        writer.write(VideoAnalytics(video_id="v-1", date="2024-01-01", views=10))
        writer.write(VideoTrafficSource(video_id="v-1", date="2024-01-01", traffic_source_type="SEARCH", views=3, updated_at=FIXED_NOW))
        writer.write(VideoTrafficSource(video_id="v-1", date="2024-01-01", traffic_source_type="EXTERNAL", views=4, updated_at=FIXED_NOW))
        views = {row["date"]: row["views"] for row in _stored("SELECT date, views FROM video_analytics")}
        self.assertEqual(views, {"2024-01-01": 10, "2024-01-02": 2})
        self.assertEqual(len(_stored("SELECT * FROM video_traffic_sources")), 2)

    def test_a_missing_key_field_is_rejected_before_any_sql(self) -> None:
        with self.assertRaises(ValueError) as raised:
            writer.write(VideoAnalytics(video_id="v-1", views=1))
        self.assertIn("date", str(raised.exception))

    def test_another_unique_constraint_is_not_treated_as_a_key(self) -> None:
        writer.write(make_video("v-1", "Alpha"))
        writer.write(make_comment_author("a-1", "Ann"))
        writer.write(make_comment("c-1", "v-1", "a-1"))
        clash = make_comment("c-2", "v-1", "a-1")
        clash.thread_id = "thread-c-1"
        with self.assertRaises(sqlite3.IntegrityError):
            writer.write(clash)
        writer.write(CommentAuthor(id="a-3", display_name="Dup", youtube_channel_id="UC-x", updated_at=FIXED_NOW))
        with self.assertRaises(sqlite3.IntegrityError):
            writer.write(CommentAuthor(id="a-4", display_name="Dup", youtube_channel_id="UC-x", updated_at=FIXED_NOW))

    def test_ownership_is_promoted_but_never_demoted(self) -> None:
        writer.write(make_video("v-1", "Referrer", own=False))
        writer.write(make_video("v-1", "Mine", own=True))
        writer.write(make_video("v-1", "Referrer again", own=False))
        writer.write(Video(id="v-1", view_count=3))
        (row,) = _stored("SELECT own, title FROM videos WHERE id = 'v-1'")
        self.assertEqual((row["own"], row["title"]), (1, "Referrer again"))

    def test_a_generated_key_row_can_be_inserted_without_its_key(self) -> None:
        run = SyncRun(batch_id="b-1", sync_type="videos", status="running", started_at=FIXED_NOW)
        self.assertEqual(writer.write(run), 1)
        (row,) = _stored("SELECT id, rows_fetched FROM sync_runs")
        self.assertEqual(row["rows_fetched"], 0)
        writer.write(SyncRun(id=row["id"], status="success"))
        (updated,) = _stored("SELECT status FROM sync_runs WHERE id = ?", row["id"])
        self.assertEqual(updated["status"], "success")

    def test_a_key_only_row_is_a_no_op_when_it_exists(self) -> None:
        writer.write(FxRate(date="2024-01-01", usd_to_sgd=1.3, updated_at=FIXED_NOW))
        self.assertEqual(writer.write(FxRate(date="2024-01-01")), 0)
        (row,) = _stored("SELECT usd_to_sgd FROM fx_rates")
        self.assertEqual(row["usd_to_sgd"], 1.3)

    def test_a_key_only_row_that_does_not_exist_is_inserted_and_meets_constraints(self) -> None:
        with self.assertRaises(sqlite3.IntegrityError):
            writer.write(FxRate(date="2024-01-01"))

    def test_values_are_bound_not_interpolated(self) -> None:
        title = "Robert'); DROP TABLE videos; --"
        statements: list[str] = []
        original = database.get_connection

        class Recording:
            """Connection stand-in that records the SQL text given to execute()."""

            def __init__(self) -> None:
                self.conn = original()

            def execute(self, sql: str, params: object = ()) -> sqlite3.Cursor:
                statements.append(sql)
                return self.conn.execute(sql, params)  # type: ignore[arg-type]

            def __getattr__(self, name: str) -> object:
                return getattr(self.conn, name)

        with mock.patch.object(writer, "get_connection", side_effect=Recording):
            writer.write(make_video("v-1", title))
        (row,) = _stored("SELECT title FROM videos WHERE id = 'v-1'")
        self.assertEqual(row["title"], title)
        self.assertTrue(any(statement.startswith("INSERT INTO videos") for statement in statements))
        self.assertTrue(all("Robert" not in statement for statement in statements))


class WriteManyTest(IsolatedDatabaseTestCase):
    def test_empty_input_returns_zero_without_a_connection(self) -> None:
        with mock.patch.object(writer, "get_connection") as get_connection:
            self.assertEqual(writer.write_many([]), 0)
        get_connection.assert_not_called()

    def test_mixed_row_classes_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            writer.write_many([make_video("v-1"), FxRate(date="2024-01-01", usd_to_sgd=1.0, updated_at=FIXED_NOW)])
        self.assertEqual(_stored("SELECT id FROM videos"), [])

    def test_returns_the_number_of_rows_processed(self) -> None:
        writer.write(make_video("v-1"))
        rows = [
            SearchTerm(video_id="v-1", month="2024-01", search_term=term, views=views, updated_at=FIXED_NOW)
            for term, views in (("cats", 3), ("dogs", 2))
        ]
        self.assertEqual(writer.write_many(rows), 2)

    def test_rows_for_one_key_apply_in_order_with_their_own_fields(self) -> None:
        writer.write_many([
            make_video("v-1", "First", view_count=1),
            Video(id="v-1", title="Second"),
            Video(id="v-1", view_count=3),
        ])
        (row,) = _stored("SELECT title, view_count FROM videos WHERE id = 'v-1'")
        self.assertEqual((row["title"], row["view_count"]), ("Second", 3))

    def test_a_late_failure_rolls_back_the_whole_batch(self) -> None:
        with self.assertRaises(sqlite3.IntegrityError):
            writer.write_many([make_video("v-1"), make_video("v-2"), Video(id="v-3", view_count=1)])
        self.assertEqual(_stored("SELECT id FROM videos"), [])

    def test_an_iterator_failure_writes_nothing(self) -> None:
        def rows() -> Iterator[Video]:
            yield make_video("v-1")
            raise RuntimeError("source failed")

        with self.assertRaises(RuntimeError):
            writer.write_many(rows())
        self.assertEqual(_stored("SELECT id FROM videos"), [])

    def test_coverage_and_related_rows_write_in_one_call(self) -> None:
        writer.write(make_video("v-1"))
        coverage = [
            SyncCoverage(collector="search_insights", video_id="v-1", period_key=month, completed_at=FIXED_NOW)
            for month in ("2024-01", "2024-02")
        ]
        related = [RelatedVideo(target_video_id="v-1", month="2024-01", referrer_video_id="ref", views=1, updated_at=FIXED_NOW)]
        self.assertEqual(writer.write_many(coverage), 2)
        self.assertEqual(writer.write_many(related), 1)


class BorrowedConnectionTest(IsolatedDatabaseTestCase):
    def test_a_connection_outside_a_transaction_is_rejected(self) -> None:
        conn = database.get_connection()
        self.addCleanup(conn.close)
        with self.assertRaises(ValueError):
            writer.write(make_video("v-1"), conn=conn)

    def test_writes_join_the_caller_transaction_without_committing_it(self) -> None:
        conn = database.get_connection()
        self.addCleanup(conn.close)
        conn.execute("BEGIN")
        writer.write(make_video("v-1"), conn=conn)
        self.assertEqual(len(conn.execute("SELECT id FROM videos").fetchall()), 1)
        conn.rollback()
        self.assertEqual(_stored("SELECT id FROM videos"), [])

    def test_a_failure_rolls_back_only_the_writer_call(self) -> None:
        conn = database.get_connection()
        self.addCleanup(conn.close)
        conn.execute("BEGIN")
        writer.write(make_video("v-1"), conn=conn)
        with self.assertRaises(sqlite3.IntegrityError):
            writer.write_many([make_video("v-2"), Video(id="v-3", view_count=1)], conn=conn)
        self.assertTrue(conn.in_transaction)
        conn.commit()
        self.assertEqual([row["id"] for row in _stored("SELECT id FROM videos")], ["v-1"])


class ConcurrentWriteTest(IsolatedDatabaseTestCase):
    def test_two_writers_on_one_new_key_produce_one_row_and_keep_ownership(self) -> None:
        start = threading.Barrier(2)
        errors: list[BaseException] = []

        def write(video: Video) -> None:
            start.wait()
            try:
                writer.write(video)
            except BaseException as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=write, args=(make_video("v-1", "Owned", own=True),)),
            threading.Thread(target=write, args=(make_video("v-1", "Referrer", own=False),)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [])
        rows = _stored("SELECT own FROM videos WHERE id = 'v-1'")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["own"], 1)


if __name__ == "__main__":
    unittest.main()
