from __future__ import annotations

import sqlite3

import database
from tests.support import IsolatedDatabaseTestCase, make_playlist, make_playlist_item, make_related_referrer, make_video


class RelatedVideosSchemaTest(IsolatedDatabaseTestCase):
    def test_table_exists(self) -> None:
        with database.get_connection() as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='related_videos'"
            ).fetchone()
        self.assertIsNotNone(row)

    def test_repeated_init_db_is_safe(self) -> None:
        database.init_db()
        database.init_db()
        with database.get_connection() as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='related_videos'"
            ).fetchone()
        self.assertIsNotNone(row)

    def _insert_related_row(self, target_video_id: str = "v-1", month: str = "2024-01",
                             referrer_video_id: str = "ref-1", views: int = 5) -> None:
        with database.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO related_videos (target_video_id, month, referrer_video_id, views, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (target_video_id, month, referrer_video_id, views, "2024-06-01T00:00:00+00:00"),
            )

    def test_unresolved_referrer_id_is_accepted_without_a_videos_row(self) -> None:
        database.upsert_own_video(make_video("v-1", "Alpha"))
        self._insert_related_row(referrer_video_id="unresolved-ref")
        with database.get_connection() as conn:
            row = conn.execute(
                "SELECT referrer_video_id FROM related_videos WHERE target_video_id = 'v-1'"
            ).fetchone()
        self.assertEqual(row["referrer_video_id"], "unresolved-ref")

    def test_target_must_reference_an_existing_video(self) -> None:
        with self.assertRaises(sqlite3.IntegrityError):
            self._insert_related_row(target_video_id="missing-target")

    def test_duplicate_target_month_referrer_is_rejected(self) -> None:
        database.upsert_own_video(make_video("v-1", "Alpha"))
        self._insert_related_row()
        with self.assertRaises(sqlite3.IntegrityError):
            self._insert_related_row()

    def test_nonpositive_views_are_rejected(self) -> None:
        database.upsert_own_video(make_video("v-1", "Alpha"))
        with self.assertRaises(sqlite3.IntegrityError):
            self._insert_related_row(views=0)
        with self.assertRaises(sqlite3.IntegrityError):
            self._insert_related_row(views=-1)

    def test_deleting_target_video_cascades_to_related_videos(self) -> None:
        database.upsert_own_video(make_video("v-1", "Alpha"))
        self._insert_related_row()
        with database.get_connection() as conn:
            conn.execute("DELETE FROM videos WHERE id = 'v-1'")
            rows = conn.execute("SELECT * FROM related_videos WHERE target_video_id = 'v-1'").fetchall()
        self.assertEqual(rows, [])

    def test_a_video_can_appear_as_both_target_and_referrer(self) -> None:
        database.upsert_own_video(make_video("v-1", "Alpha"))
        database.upsert_own_video(make_video("v-2", "Beta"))
        self._insert_related_row(target_video_id="v-1", referrer_video_id="v-2")
        self._insert_related_row(target_video_id="v-2", referrer_video_id="v-1")
        with database.get_connection() as conn:
            rows = conn.execute("SELECT target_video_id, referrer_video_id FROM related_videos").fetchall()
        self.assertEqual(len(rows), 2)


class UpsertRelatedVideosTest(IsolatedDatabaseTestCase):
    def setUp(self) -> None:
        super().setUp()
        database.upsert_own_video(make_video("v-1", "Alpha"))

    def _stored_referrers(self, target_video_id: str = "v-1", month: str = "2024-01") -> dict[str, int]:
        with database.get_connection() as conn:
            rows = conn.execute(
                "SELECT referrer_video_id, views FROM related_videos WHERE target_video_id = ? AND month = ?",
                (target_video_id, month),
            ).fetchall()
        return {r["referrer_video_id"]: r["views"] for r in rows}

    def test_rejects_invalid_month_format(self) -> None:
        with self.assertRaises(ValueError):
            database.upsert_related_videos("v-1", "2024-1", [make_related_referrer("ref-1", views=5)])

    def test_two_distinct_months_are_stored_independently(self) -> None:
        database.upsert_related_videos("v-1", "2024-01", [make_related_referrer("ref-1", views=5)])
        database.upsert_related_videos("v-1", "2024-02", [make_related_referrer("ref-2", views=7)])
        self.assertEqual(self._stored_referrers(month="2024-01"), {"ref-1": 5})
        self.assertEqual(self._stored_referrers(month="2024-02"), {"ref-2": 7})

    def test_upsert_refreshes_an_unchanged_referrer_and_still_counts_it(self) -> None:
        database.upsert_related_videos("v-1", "2024-01", [make_related_referrer("ref-1", views=5)])
        rows_written = database.upsert_related_videos("v-1", "2024-01", [make_related_referrer("ref-1", views=5)])
        self.assertEqual(rows_written, 1)
        self.assertEqual(self._stored_referrers(), {"ref-1": 5})

    def test_upsert_updates_a_changed_referrer_view_count(self) -> None:
        database.upsert_related_videos("v-1", "2024-01", [make_related_referrer("ref-1", views=5)])
        database.upsert_related_videos("v-1", "2024-01", [make_related_referrer("ref-1", views=9)])
        self.assertEqual(self._stored_referrers(), {"ref-1": 9})

    def test_referrers_omitted_by_a_later_response_are_retained(self) -> None:
        database.upsert_related_videos("v-1", "2024-01", [
            make_related_referrer("ref-1", views=5),
            make_related_referrer("ref-2", views=3),
        ])
        database.upsert_related_videos("v-1", "2024-01", [make_related_referrer("ref-1", views=6)])
        self.assertEqual(self._stored_referrers(), {"ref-1": 6, "ref-2": 3})

    def test_duplicate_exact_referrer_keys_in_one_response_are_summed(self) -> None:
        database.upsert_related_videos("v-1", "2024-01", [
            make_related_referrer("ref-1", views=5),
            make_related_referrer("ref-1", views=3),
        ])
        self.assertEqual(self._stored_referrers(), {"ref-1": 8})

    def test_zero_and_negative_view_referrers_are_dropped_not_stored(self) -> None:
        rows_written = database.upsert_related_videos("v-1", "2024-01", [
            make_related_referrer("ref-1", views=0),
            make_related_referrer("ref-2", views=-1),
        ])
        self.assertEqual(rows_written, 0)
        self.assertEqual(self._stored_referrers(), {})

    def test_empty_response_is_a_no_op(self) -> None:
        rows_written = database.upsert_related_videos("v-1", "2024-01", [])
        self.assertEqual(rows_written, 0)
        self.assertEqual(self._stored_referrers(), {})

    def test_raises_for_a_target_that_does_not_exist(self) -> None:
        with self.assertRaises(ValueError):
            database.upsert_related_videos("missing-target", "2024-01", [make_related_referrer("ref-1", views=5)])

    def test_raises_for_a_target_that_is_not_owned(self) -> None:
        database.upsert_own_video(make_video("v-external", "External"))
        with database.get_connection() as conn:
            conn.execute("UPDATE videos SET own = 0 WHERE id = 'v-external'")
        with self.assertRaises(ValueError):
            database.upsert_related_videos("v-external", "2024-01", [make_related_referrer("ref-1", views=5)])

    def test_validation_failure_rolls_back_the_whole_call(self) -> None:
        with self.assertRaises(ValueError):
            database.upsert_related_videos("v-1", "2024-01", [
                make_related_referrer("ref-1", views=5),
                {"referrer_video_id": "ref-2", "views": "not-an-int"},
            ])
        self.assertEqual(self._stored_referrers(), {})


class GetLastRelatedVideosMonthTest(IsolatedDatabaseTestCase):
    def setUp(self) -> None:
        super().setUp()
        database.upsert_own_video(make_video("v-1", "Alpha"))

    def test_returns_none_when_no_rows(self) -> None:
        self.assertIsNone(database.get_last_related_videos_month("v-1"))

    def test_returns_the_latest_stored_month(self) -> None:
        database.upsert_related_videos("v-1", "2024-01", [make_related_referrer("ref-1", views=5)])
        database.upsert_related_videos("v-1", "2024-03", [make_related_referrer("ref-2", views=5)])
        database.upsert_related_videos("v-1", "2024-02", [make_related_referrer("ref-3", views=5)])
        self.assertEqual(database.get_last_related_videos_month("v-1"), "2024-03")


class GetRelatedVideoReferrersTest(IsolatedDatabaseTestCase):
    def setUp(self) -> None:
        super().setUp()
        database.upsert_own_video(make_video("v-1", "Target One", content_type="video", privacy_status="public"))
        database.upsert_own_video(make_video("v-2", "Target Two", content_type="short", privacy_status="private"))
        # A referrer confirmed as this channel's own video.
        database.upsert_own_video(make_video("ref-mine", "My Own Referrer"))
        # A referrer resolved as belonging to another channel.
        database.upsert_own_video(make_video("ref-external", "External Referrer"))
        with database.get_connection() as conn:
            conn.execute("UPDATE videos SET own = 0 WHERE id = 'ref-external'")

    def test_sums_across_months_and_referrers(self) -> None:
        database.upsert_related_videos("v-1", "2024-01", [make_related_referrer("ref-mine", views=5)])
        database.upsert_related_videos("v-1", "2024-02", [make_related_referrer("ref-mine", views=7)])
        result = database.get_related_video_referrers()
        self.assertEqual(result["items"][0]["referrer_video_id"], "ref-mine")
        self.assertEqual(result["items"][0]["views"], 12)

    def test_boundary_dates_include_the_whole_containing_month(self) -> None:
        database.upsert_related_videos("v-1", "2024-01", [make_related_referrer("ref-mine", views=5)])
        result = database.get_related_video_referrers(start_date="2024-01-20", end_date="2024-01-25")
        self.assertEqual(result["items"][0]["views"], 5)

    def test_missing_month_outside_bounds_is_excluded(self) -> None:
        database.upsert_related_videos("v-1", "2024-01", [make_related_referrer("ref-mine", views=5)])
        result = database.get_related_video_referrers(start_date="2024-02-01", end_date="2024-02-28")
        self.assertEqual(result["items"], [])
        self.assertEqual(result["total_named_views"], 0)

    def test_malformed_start_date_returns_no_rows_instead_of_a_broad_lexical_match(self) -> None:
        database.upsert_related_videos("v-1", "2024-01", [make_related_referrer("ref-mine", views=5)])
        result = database.get_related_video_referrers(start_date="2024", end_date="2024-12-31")
        self.assertEqual(result["items"], [])
        self.assertEqual(result["total_named_views"], 0)

    def test_own_true_excludes_external_and_unresolved(self) -> None:
        database.upsert_related_videos("v-1", "2024-01", [
            make_related_referrer("ref-mine", views=5),
            make_related_referrer("ref-external", views=7),
            make_related_referrer("ref-unresolved", views=3),
        ])
        result = database.get_related_video_referrers(own=True)
        self.assertEqual([r["referrer_video_id"] for r in result["items"]], ["ref-mine"])

    def test_own_false_includes_external_and_unresolved(self) -> None:
        database.upsert_related_videos("v-1", "2024-01", [
            make_related_referrer("ref-mine", views=5),
            make_related_referrer("ref-external", views=7),
            make_related_referrer("ref-unresolved", views=3),
        ])
        result = database.get_related_video_referrers(own=False)
        ids = {r["referrer_video_id"] for r in result["items"]}
        self.assertEqual(ids, {"ref-external", "ref-unresolved"})

    def test_own_none_returns_everything(self) -> None:
        database.upsert_related_videos("v-1", "2024-01", [
            make_related_referrer("ref-mine", views=5),
            make_related_referrer("ref-external", views=7),
            make_related_referrer("ref-unresolved", views=3),
        ])
        result = database.get_related_video_referrers(own=None)
        ids = {r["referrer_video_id"] for r in result["items"]}
        self.assertEqual(ids, {"ref-mine", "ref-external", "ref-unresolved"})

    def test_total_named_views_is_independent_of_own_filter_and_limit(self) -> None:
        database.upsert_related_videos("v-1", "2024-01", [
            make_related_referrer("ref-mine", views=5),
            make_related_referrer("ref-external", views=7),
            make_related_referrer("ref-unresolved", views=3),
        ])
        own_true = database.get_related_video_referrers(own=True, limit=1)
        own_false = database.get_related_video_referrers(own=False, limit=1)
        own_none = database.get_related_video_referrers(own=None)
        self.assertEqual(own_true["total_named_views"], 15)
        self.assertEqual(own_false["total_named_views"], 15)
        self.assertEqual(own_none["total_named_views"], 15)

    def test_limit_caps_items(self) -> None:
        database.upsert_related_videos("v-1", "2024-01", [
            make_related_referrer("ref-mine", views=5),
            make_related_referrer("ref-external", views=7),
            make_related_referrer("ref-unresolved", views=3),
        ])
        result = database.get_related_video_referrers(limit=2)
        self.assertEqual(len(result["items"]), 2)

    def test_ordering_is_views_desc_then_referrer_id_asc(self) -> None:
        database.upsert_related_videos("v-1", "2024-01", [
            make_related_referrer("ref-b", views=5),
            make_related_referrer("ref-a", views=5),
            make_related_referrer("ref-mine", views=9),
        ])
        result = database.get_related_video_referrers()
        ids = [r["referrer_video_id"] for r in result["items"]]
        self.assertEqual(ids, ["ref-mine", "ref-a", "ref-b"])

    def test_video_ids_none_covers_every_owned_target(self) -> None:
        database.upsert_related_videos("v-1", "2024-01", [make_related_referrer("ref-mine", views=5)])
        database.upsert_related_videos("v-2", "2024-01", [make_related_referrer("ref-mine", views=4)])
        result = database.get_related_video_referrers(video_ids=None)
        self.assertEqual(result["items"][0]["views"], 9)

    def test_video_ids_populated_scopes_to_those_targets(self) -> None:
        database.upsert_related_videos("v-1", "2024-01", [make_related_referrer("ref-mine", views=5)])
        database.upsert_related_videos("v-2", "2024-01", [make_related_referrer("ref-mine", views=4)])
        result = database.get_related_video_referrers(video_ids=["v-1"])
        self.assertEqual(result["items"][0]["views"], 5)

    def test_video_ids_empty_returns_nothing(self) -> None:
        database.upsert_related_videos("v-1", "2024-01", [make_related_referrer("ref-mine", views=5)])
        result = database.get_related_video_referrers(video_ids=[])
        self.assertEqual(result, {"items": [], "total_named_views": 0})

    def test_content_type_and_privacy_status_filter_the_target_side(self) -> None:
        database.upsert_related_videos("v-1", "2024-01", [make_related_referrer("ref-mine", views=5)])
        database.upsert_related_videos("v-2", "2024-01", [make_related_referrer("ref-mine", views=4)])
        result = database.get_related_video_referrers(content_type="short", privacy_status="private")
        self.assertEqual(result["items"][0]["views"], 4)

    def test_unresolved_referrer_has_null_metadata_and_none_own(self) -> None:
        database.upsert_related_videos("v-1", "2024-01", [make_related_referrer("ref-unresolved", views=3)])
        result = database.get_related_video_referrers()
        item = result["items"][0]
        self.assertIsNone(item["title"])
        self.assertIsNone(item["thumbnail_url"])
        self.assertIsNone(item["referrer_own"])

    def test_resolved_referrer_own_is_a_real_boolean(self) -> None:
        database.upsert_related_videos("v-1", "2024-01", [
            make_related_referrer("ref-mine", views=5),
            make_related_referrer("ref-external", views=7),
        ])
        result = database.get_related_video_referrers()
        by_id = {r["referrer_video_id"]: r for r in result["items"]}
        self.assertIs(by_id["ref-mine"]["referrer_own"], True)
        self.assertIs(by_id["ref-external"]["referrer_own"], False)


class GetRelatedVideoDestinationsTest(IsolatedDatabaseTestCase):
    def setUp(self) -> None:
        super().setUp()
        database.upsert_own_video(make_video("v-1", "Target One"))
        database.upsert_own_video(make_video("v-2", "Target Two"))
        database.upsert_own_video(make_video("ref-mine", "My Own Referrer"))
        database.upsert_own_video(make_video("ref-external", "External Referrer"))
        with database.get_connection() as conn:
            conn.execute("UPDATE videos SET own = 0 WHERE id = 'ref-external'")

    def test_scopes_to_a_single_referrer(self) -> None:
        database.upsert_related_videos("v-1", "2024-01", [make_related_referrer("ref-mine", views=5)])
        database.upsert_related_videos("v-2", "2024-01", [make_related_referrer("ref-external", views=9)])
        result = database.get_related_video_destinations("ref-mine")
        self.assertEqual([r["target_video_id"] for r in result], ["v-1"])

    def test_works_identically_for_an_external_referrer(self) -> None:
        database.upsert_related_videos("v-1", "2024-01", [make_related_referrer("ref-external", views=9)])
        result = database.get_related_video_destinations("ref-external")
        self.assertEqual([r["target_video_id"] for r in result], ["v-1"])

    def test_limit_caps_results(self) -> None:
        database.upsert_related_videos("v-1", "2024-01", [make_related_referrer("ref-mine", views=5)])
        database.upsert_related_videos("v-2", "2024-01", [make_related_referrer("ref-mine", views=9)])
        result = database.get_related_video_destinations("ref-mine", limit=1)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["target_video_id"], "v-2")

    def test_ordering_is_views_desc_then_target_id_asc(self) -> None:
        database.upsert_related_videos("v-1", "2024-01", [make_related_referrer("ref-mine", views=5)])
        database.upsert_related_videos("v-2", "2024-01", [make_related_referrer("ref-mine", views=5)])
        result = database.get_related_video_destinations("ref-mine")
        self.assertEqual([r["target_video_id"] for r in result], ["v-1", "v-2"])

    def test_video_ids_scopes_the_destination_set(self) -> None:
        database.upsert_related_videos("v-1", "2024-01", [make_related_referrer("ref-mine", views=5)])
        database.upsert_related_videos("v-2", "2024-01", [make_related_referrer("ref-mine", views=9)])
        result = database.get_related_video_destinations("ref-mine", video_ids=["v-1"])
        self.assertEqual([r["target_video_id"] for r in result], ["v-1"])

    def test_video_ids_empty_returns_nothing(self) -> None:
        database.upsert_related_videos("v-1", "2024-01", [make_related_referrer("ref-mine", views=5)])
        result = database.get_related_video_destinations("ref-mine", video_ids=[])
        self.assertEqual(result, [])

    def test_playlist_membership_deduplicates_destinations(self) -> None:
        database.upsert_playlist(make_playlist("p-1", "Playlist"))
        database.upsert_playlist_item(make_playlist_item("pi-1", "p-1", "v-1", 0))
        database.upsert_playlist_item(make_playlist_item("pi-2", "p-1", "v-1", 1))
        database.upsert_related_videos("v-1", "2024-01", [make_related_referrer("ref-mine", views=5)])
        playlist_video_ids = database.get_playlist_video_ids("p-1")
        result = database.get_related_video_destinations("ref-mine", video_ids=playlist_video_ids)
        self.assertEqual(len(result), 1)

    def test_no_rows_for_unknown_referrer(self) -> None:
        database.upsert_related_videos("v-1", "2024-01", [make_related_referrer("ref-mine", views=5)])
        self.assertEqual(database.get_related_video_destinations("does-not-exist"), [])
