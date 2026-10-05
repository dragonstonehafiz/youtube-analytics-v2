from __future__ import annotations

import copy
import unittest

from database import RelatedVideo, SearchTerm
from sync.write_preparation import related_video_rows, search_term_rows

NOW = "2024-06-01T00:00:00+00:00"


class SearchTermRowsTest(unittest.TestCase):
    def test_builds_one_row_per_term_with_the_video_month_and_timestamp(self) -> None:
        rows = search_term_rows("v-1", "2024-01", [{"search_term": "cats", "views": 3}], updated_at=NOW)
        self.assertEqual(rows, [SearchTerm(video_id="v-1", month="2024-01", search_term="cats", views=3, updated_at=NOW)])

    def test_duplicate_terms_are_summed_in_first_seen_order(self) -> None:
        terms = [
            {"search_term": "dogs", "views": 1},
            {"search_term": "cats", "views": 2},
            {"search_term": "dogs", "views": 4},
        ]
        rows = search_term_rows("v-1", "2024-01", terms, updated_at=NOW)
        self.assertEqual([(row.search_term, row.views) for row in rows], [("dogs", 5), ("cats", 2)])

    def test_terms_with_zero_or_negative_totals_are_dropped(self) -> None:
        terms = [
            {"search_term": "zero", "views": 0},
            {"search_term": "negative", "views": -2},
            {"search_term": "cancels", "views": 3},
            {"search_term": "cancels", "views": -3},
            {"search_term": "kept", "views": 1},
        ]
        rows = search_term_rows("v-1", "2024-01", terms, updated_at=NOW)
        self.assertEqual([row.search_term for row in rows], ["kept"])

    def test_invalid_payloads_raise(self) -> None:
        cases: dict[str, tuple[str, list[dict]]] = {
            "bad month": ("2024-13", [{"search_term": "cats", "views": 1}]),
            "empty term": ("2024-01", [{"search_term": "", "views": 1}]),
            "non-string term": ("2024-01", [{"search_term": 7, "views": 1}]),
            "bool views": ("2024-01", [{"search_term": "cats", "views": True}]),
            "float views": ("2024-01", [{"search_term": "cats", "views": 1.5}]),
        }
        for name, (month, terms) in cases.items():
            with self.subTest(name), self.assertRaises(ValueError):
                search_term_rows("v-1", month, terms, updated_at=NOW)

    def test_one_invalid_row_rejects_the_whole_payload(self) -> None:
        terms = [{"search_term": "cats", "views": 1}, {"search_term": "", "views": 1}]
        with self.assertRaises(ValueError):
            search_term_rows("v-1", "2024-01", terms, updated_at=NOW)

    def test_the_payload_is_not_mutated(self) -> None:
        terms = [{"search_term": "cats", "views": 1}, {"search_term": "cats", "views": 2}]
        before = copy.deepcopy(terms)
        search_term_rows("v-1", "2024-01", terms, updated_at=NOW)
        self.assertEqual(terms, before)


class RelatedVideoRowsTest(unittest.TestCase):
    def test_builds_summed_positive_rows_for_the_target_month(self) -> None:
        referrers = [
            {"referrer_video_id": "ref-a", "views": 2},
            {"referrer_video_id": "ref-b", "views": 0},
            {"referrer_video_id": "ref-a", "views": 3},
        ]
        rows = related_video_rows("v-1", "2024-01", referrers, updated_at=NOW)
        self.assertEqual(rows, [
            RelatedVideo(target_video_id="v-1", month="2024-01", referrer_video_id="ref-a", views=5, updated_at=NOW),
        ])

    def test_invalid_payloads_raise(self) -> None:
        cases: dict[str, tuple[str, list[dict]]] = {
            "bad month": ("24-01", [{"referrer_video_id": "ref", "views": 1}]),
            "empty referrer": ("2024-01", [{"referrer_video_id": "", "views": 1}]),
            "bool views": ("2024-01", [{"referrer_video_id": "ref", "views": False}]),
        }
        for name, (month, referrers) in cases.items():
            with self.subTest(name), self.assertRaises(ValueError):
                related_video_rows("v-1", month, referrers, updated_at=NOW)

    def test_an_empty_payload_gives_no_rows(self) -> None:
        self.assertEqual(related_video_rows("v-1", "2024-01", [], updated_at=NOW), [])


if __name__ == "__main__":
    unittest.main()
