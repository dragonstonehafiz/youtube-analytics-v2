from __future__ import annotations

import unittest

import database
from tests.support import IsolatedDatabaseTestCase, make_video


class SearchTermsSchemaTest(IsolatedDatabaseTestCase):
    def test_schema_initializes_idempotently_against_an_existing_database(self) -> None:
        database.init_db()
        with database.get_connection() as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='search_terms'"
            ).fetchone()
        self.assertIsNotNone(row)

    def test_video_deletion_cascades_to_search_terms(self) -> None:
        database.upsert_own_video(make_video("v-1", "Alpha"))
        database.upsert_search_terms("v-1", "2024-01", [{"search_term": "cats", "views": 5}])
        with database.get_connection() as conn:
            conn.execute("DELETE FROM videos WHERE id = 'v-1'")
            rows = conn.execute("SELECT * FROM search_terms WHERE video_id = 'v-1'").fetchall()
        self.assertEqual(rows, [])


class UpsertSearchTermsTest(IsolatedDatabaseTestCase):
    def setUp(self) -> None:
        super().setUp()
        database.upsert_own_video(make_video("v-1", "Alpha"))

    def _stored_terms(self, video_id: str = "v-1", month: str = "2024-01") -> dict[str, int]:
        with database.get_connection() as conn:
            rows = conn.execute(
                "SELECT search_term, views FROM search_terms WHERE video_id = ? AND month = ?",
                (video_id, month),
            ).fetchall()
        return {r["search_term"]: r["views"] for r in rows}

    def test_rejects_invalid_month_format(self) -> None:
        with self.assertRaises(ValueError):
            database.upsert_search_terms("v-1", "2024-1", [{"search_term": "cats", "views": 5}])

    def test_two_distinct_months_are_stored_independently(self) -> None:
        database.upsert_search_terms("v-1", "2024-01", [{"search_term": "cats", "views": 5}])
        database.upsert_search_terms("v-1", "2024-02", [{"search_term": "dogs", "views": 7}])
        self.assertEqual(self._stored_terms(month="2024-01"), {"cats": 5})
        self.assertEqual(self._stored_terms(month="2024-02"), {"dogs": 7})

    def test_upsert_refreshes_an_unchanged_term_and_still_counts_it(self) -> None:
        database.upsert_search_terms("v-1", "2024-01", [{"search_term": "cats", "views": 5}])
        rows_written = database.upsert_search_terms("v-1", "2024-01", [{"search_term": "cats", "views": 5}])
        self.assertEqual(rows_written, 1)
        self.assertEqual(self._stored_terms(), {"cats": 5})

    def test_upsert_updates_a_changed_term_count(self) -> None:
        database.upsert_search_terms("v-1", "2024-01", [{"search_term": "cats", "views": 5}])
        database.upsert_search_terms("v-1", "2024-01", [{"search_term": "cats", "views": 9}])
        self.assertEqual(self._stored_terms(), {"cats": 9})

    def test_terms_omitted_by_a_later_response_are_retained(self) -> None:
        database.upsert_search_terms("v-1", "2024-01", [
            {"search_term": "cats", "views": 5},
            {"search_term": "dogs", "views": 3},
        ])
        database.upsert_search_terms("v-1", "2024-01", [{"search_term": "cats", "views": 6}])
        self.assertEqual(self._stored_terms(), {"cats": 6, "dogs": 3})

    def test_duplicate_exact_term_keys_in_one_response_are_summed(self) -> None:
        database.upsert_search_terms("v-1", "2024-01", [
            {"search_term": "cats", "views": 5},
            {"search_term": "cats", "views": 3},
        ])
        self.assertEqual(self._stored_terms(), {"cats": 8})

    def test_zero_and_negative_view_terms_are_dropped_not_stored(self) -> None:
        rows_written = database.upsert_search_terms("v-1", "2024-01", [
            {"search_term": "cats", "views": 0},
            {"search_term": "dogs", "views": -1},
        ])
        self.assertEqual(rows_written, 0)
        self.assertEqual(self._stored_terms(), {})

    def test_a_literal_term_named_other_unattributed_is_stored_as_a_real_term(self) -> None:
        database.upsert_search_terms("v-1", "2024-01", [{"search_term": "Other / unattributed", "views": 4}])
        self.assertEqual(self._stored_terms(), {"Other / unattributed": 4})

    def test_successful_empty_response_is_a_no_op(self) -> None:
        database.upsert_search_terms("v-1", "2024-01", [{"search_term": "cats", "views": 5}])
        rows_written = database.upsert_search_terms("v-1", "2024-01", [])
        self.assertEqual(rows_written, 0)
        self.assertEqual(self._stored_terms(), {"cats": 5})

    def test_malformed_row_raises_and_writes_nothing(self) -> None:
        with self.assertRaises(ValueError):
            database.upsert_search_terms("v-1", "2024-01", [
                {"search_term": "cats", "views": 5},
                {"search_term": "", "views": 3},
            ])
        self.assertEqual(self._stored_terms(), {})

    def test_non_integer_views_raises_and_writes_nothing(self) -> None:
        with self.assertRaises(ValueError):
            database.upsert_search_terms("v-1", "2024-01", [{"search_term": "cats", "views": "5"}])
        self.assertEqual(self._stored_terms(), {})

    def test_rollback_on_write_error_preserves_prior_state_and_partial_batch(self) -> None:
        database.upsert_search_terms("v-1", "2024-01", [{"search_term": "cats", "views": 5}])
        with self.assertRaises(Exception):
            database.upsert_search_terms("missing-video", "2024-01", [{"search_term": "dogs", "views": 3}])
        self.assertEqual(self._stored_terms(), {"cats": 5})
        with database.get_connection() as conn:
            rows = conn.execute("SELECT * FROM search_terms WHERE video_id = 'missing-video'").fetchall()
        self.assertEqual(rows, [])

    def test_rows_written_counts_direct_upserts_only(self) -> None:
        rows_written = database.upsert_search_terms("v-1", "2024-01", [
            {"search_term": "cats", "views": 5},
            {"search_term": "dogs", "views": 3},
        ])
        self.assertEqual(rows_written, 2)


class SearchInsightsReportingTestCase(IsolatedDatabaseTestCase):
    """Runs against a throwaway SQLite file so the app database is never touched."""

    def setUp(self) -> None:
        super().setUp()
        database.upsert_own_video(make_video("v-1", "Alpha Episode", content_type="video", privacy_status="public"))
        database.upsert_own_video(make_video("v-2", "Beta Vlog", content_type="short", privacy_status="private"))
        database.upsert_own_video(make_video("v-3", "Unclassified Clip", content_type=None, privacy_status="public"))

        database.upsert_search_terms("v-1", "2024-01", [
            {"search_term": "cats", "views": 10},
            {"search_term": "dogs", "views": 5},
        ])
        database.upsert_search_terms("v-2", "2024-01", [{"search_term": "cats", "views": 3}])
        database.upsert_search_terms("v-1", "2024-02", [{"search_term": "cats", "views": 4}])
        database.upsert_search_terms("v-3", "2024-01", [{"search_term": "birds", "views": 7}])


class GetSearchTermsTest(SearchInsightsReportingTestCase):
    def test_sums_views_for_one_term_across_videos_and_months(self) -> None:
        rows = database.get_search_terms(start_date="2024-01-01", end_date="2024-02-29")
        by_term = {r["search_term"]: r["views"] for r in rows}
        self.assertEqual(by_term["cats"], 17)

    def test_orders_by_views_descending_then_term_ascending(self) -> None:
        rows = database.get_search_terms(start_date="2024-01-01", end_date="2024-02-29")
        self.assertEqual([r["search_term"] for r in rows], ["cats", "birds", "dogs"])

    def test_ties_break_by_term_text(self) -> None:
        database.upsert_search_terms("v-2", "2024-01", [{"search_term": "ants", "views": 7}])
        rows = database.get_search_terms(start_date="2024-01-01", end_date="2024-01-31")
        tied = [r["search_term"] for r in rows if r["views"] == 7]
        self.assertEqual(tied, ["ants", "birds"])

    def test_no_limit_returns_every_term(self) -> None:
        rows = database.get_search_terms(start_date="2024-01-01", end_date="2024-02-29")
        self.assertEqual(len(rows), 3)

    def test_limit_truncates_results(self) -> None:
        rows = database.get_search_terms(start_date="2024-01-01", end_date="2024-02-29", limit=1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["search_term"], "cats")

    def test_content_type_filter_scopes_to_matching_videos(self) -> None:
        rows = database.get_search_terms(start_date="2024-01-01", end_date="2024-01-31", content_type="short")
        self.assertEqual([(r["search_term"], r["views"]) for r in rows], [("cats", 3)])

    def test_privacy_status_filter_scopes_to_matching_videos(self) -> None:
        rows = database.get_search_terms(start_date="2024-01-01", end_date="2024-01-31", privacy_status="private")
        self.assertEqual([(r["search_term"], r["views"]) for r in rows], [("cats", 3)])

    def test_title_filter_matches_substring_case_insensitively_on_video_title_not_term(self) -> None:
        rows = database.get_search_terms(start_date="2024-01-01", end_date="2024-01-31", title="alpha")
        self.assertEqual({r["search_term"] for r in rows}, {"cats", "dogs"})

    def test_video_ids_scope_limits_to_those_videos(self) -> None:
        rows = database.get_search_terms(start_date="2024-01-01", end_date="2024-01-31", video_ids=["v-2"])
        self.assertEqual([(r["search_term"], r["views"]) for r in rows], [("cats", 3)])

    def test_empty_video_ids_scope_returns_no_rows(self) -> None:
        rows = database.get_search_terms(start_date="2024-01-01", end_date="2024-01-31", video_ids=[])
        self.assertEqual(rows, [])

    def test_missing_end_date_is_unbounded_on_that_side(self) -> None:
        rows = database.get_search_terms(start_date="2024-01-01")
        by_term = {r["search_term"]: r["views"] for r in rows}
        self.assertEqual(by_term, {"cats": 17, "dogs": 5, "birds": 7})

    def test_missing_start_date_is_unbounded_on_that_side(self) -> None:
        rows = database.get_search_terms(end_date="2024-01-31")
        by_term = {r["search_term"]: r["views"] for r in rows}
        self.assertEqual(by_term, {"cats": 13, "dogs": 5, "birds": 7})

    def test_start_date_after_end_date_returns_no_rows(self) -> None:
        rows = database.get_search_terms(start_date="2024-02-01", end_date="2024-01-01")
        self.assertEqual(rows, [])

    def test_month_outside_range_is_excluded(self) -> None:
        rows = database.get_search_terms(start_date="2024-01-01", end_date="2024-01-31")
        by_term = {r["search_term"]: r["views"] for r in rows}
        self.assertEqual(by_term["cats"], 13)

    def test_boundary_dates_within_a_month_still_include_the_whole_month(self) -> None:
        rows = database.get_search_terms(start_date="2024-01-15", end_date="2024-01-20")
        by_term = {r["search_term"]: r["views"] for r in rows}
        self.assertEqual(by_term["cats"], 13)

    def test_malformed_start_date_returns_no_rows_instead_of_a_broad_lexical_match(self) -> None:
        rows = database.get_search_terms(start_date="2024", end_date="2024-12-31")
        self.assertEqual(rows, [])

    def test_malformed_end_date_returns_no_rows(self) -> None:
        rows = database.get_search_terms(start_date="2024-01-01", end_date="not-a-date")
        self.assertEqual(rows, [])


class GetVideoSearchTermsTest(SearchInsightsReportingTestCase):
    def test_returns_only_that_videos_terms_summed_across_months(self) -> None:
        rows = database.get_video_search_terms("v-1", start_date="2024-01-01", end_date="2024-02-29")
        by_term = {r["search_term"]: r["views"] for r in rows}
        self.assertEqual(by_term, {"cats": 14, "dogs": 5})

    def test_orders_by_views_descending(self) -> None:
        rows = database.get_video_search_terms("v-1", start_date="2024-01-01", end_date="2024-02-29")
        self.assertEqual([r["search_term"] for r in rows], ["cats", "dogs"])

    def test_limit_truncates_results(self) -> None:
        rows = database.get_video_search_terms("v-1", start_date="2024-01-01", end_date="2024-02-29", limit=1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["search_term"], "cats")

    def test_missing_dates_return_every_month(self) -> None:
        rows = database.get_video_search_terms("v-1")
        by_term = {r["search_term"]: r["views"] for r in rows}
        self.assertEqual(by_term, {"cats": 14, "dogs": 5})

    def test_other_videos_terms_are_excluded(self) -> None:
        rows = database.get_video_search_terms("v-2", start_date="2024-01-01", end_date="2024-01-31")
        self.assertEqual([(r["search_term"], r["views"]) for r in rows], [("cats", 3)])


class GetVideosBySearchTermTest(SearchInsightsReportingTestCase):
    def test_returns_only_videos_matching_the_given_term(self) -> None:
        videos = database.get_videos_by_search_term("cats", start_date="2024-01-01", end_date="2024-02-29")
        self.assertEqual({v["id"] for v in videos}, {"v-1", "v-2"})

    def test_orders_by_views_descending(self) -> None:
        videos = database.get_videos_by_search_term("cats", start_date="2024-01-01", end_date="2024-02-29")
        self.assertEqual([v["id"] for v in videos], ["v-1", "v-2"])

    def test_limit_truncates_results(self) -> None:
        videos = database.get_videos_by_search_term("cats", start_date="2024-01-01", end_date="2024-02-29", limit=1)
        self.assertEqual(len(videos), 1)
        self.assertEqual(videos[0]["id"], "v-1")

    def test_unknown_term_returns_no_videos(self) -> None:
        videos = database.get_videos_by_search_term("nonexistent", start_date="2024-01-01", end_date="2024-01-31")
        self.assertEqual(videos, [])

    def test_empty_video_ids_scope_returns_no_videos(self) -> None:
        videos = database.get_videos_by_search_term("cats", start_date="2024-01-01", end_date="2024-01-31", video_ids=[])
        self.assertEqual(videos, [])

    def test_missing_dates_return_every_month(self) -> None:
        videos = database.get_videos_by_search_term("cats")
        self.assertEqual([v["id"] for v in videos], ["v-1", "v-2"])


if __name__ == "__main__":
    unittest.main()
