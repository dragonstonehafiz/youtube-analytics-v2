"""Connection timeouts on Data and Analytics API requests, through the real Google client with a scripted transport."""

from __future__ import annotations

import json
import unittest
from typing import Any
from unittest import mock

import httplib2
from googleapiclient.discovery import build

from database import SyncRun, reader
from sync import orchestration, status
from sync.stages import SyncCounts
from tests.support import IsolatedDatabaseTestCase
from youtube import analytics_api, data_api
from youtube.retries import MAX_ATTEMPTS

_REPORT_HEADERS = [{"name": "day"}, {"name": "views"}]


class _ScriptedHttp:
    """httplib2 stand-in: each request raises or answers with the next scripted step."""

    def __init__(self, steps: list[Exception | dict]) -> None:
        self.steps = list(steps)
        self.requests = 0

    def request(self, uri: str, method: str = "GET", *args: Any, **kwargs: Any) -> tuple[httplib2.Response, bytes]:
        self.requests += 1
        step = self.steps.pop(0)
        if isinstance(step, Exception):
            raise step
        return httplib2.Response({"status": "200"}), json.dumps(step).encode()


def _report(rows: list[list]) -> dict:
    return {"columnHeaders": _REPORT_HEADERS, "rows": rows}


def _playlists_page(playlist_id: str, next_page_token: str | None) -> dict:
    page: dict = {"items": [{"id": playlist_id, "snippet": {}, "contentDetails": {}}]}
    if next_page_token:
        page["nextPageToken"] = next_page_token
    return page


def _analytics_service(http: _ScriptedHttp) -> Any:
    return build("youtubeAnalytics", "v2", http=http, static_discovery=True)


def _data_service(http: _ScriptedHttp) -> Any:
    return build("youtube", "v3", http=http, static_discovery=True)


class _NoWaitTestCase(unittest.TestCase):
    """Patches time.sleep, which both the client's and _analytics_query()'s retries call."""

    def setUp(self) -> None:
        super().setUp()
        mock.patch("time.sleep").start()
        self.addCleanup(mock.patch.stopall)


class AnalyticsConnectionRetryTest(_NoWaitTestCase):
    def test_timeouts_then_success_return_the_report(self) -> None:
        http = _ScriptedHttp([TimeoutError(), TimeoutError(), _report([["2024-01-01", 5]])])

        # The client retried twice; _analytics_query()'s HttpError loop logged nothing.
        with self.assertNoLogs("youtube_analytics.sync", level="WARNING"):
            with self.assertLogs("googleapiclient.http", level="WARNING") as logs:
                result = analytics_api._analytics_query(_analytics_service(http), {"ids": "channel==MINE"})

        self.assertEqual(result["rows"], [["2024-01-01", 5]])
        self.assertEqual(http.requests, 3)
        self.assertEqual(sum("before retry" in line for line in logs.output), 2)

    def test_connection_errors_are_retried_like_timeouts(self) -> None:
        http = _ScriptedHttp([ConnectionResetError(), _report([])])

        analytics_api._analytics_query(_analytics_service(http), {"ids": "channel==MINE"})

        self.assertEqual(http.requests, 2)

    def test_timeouts_on_every_attempt_raise_after_the_shared_budget(self) -> None:
        http = _ScriptedHttp([TimeoutError()] * MAX_ATTEMPTS)

        with self.assertRaises(TimeoutError):
            analytics_api._analytics_query(_analytics_service(http), {"ids": "channel==MINE"})

        self.assertEqual(http.requests, MAX_ATTEMPTS)


class DataConnectionRetryTest(_NoWaitTestCase):
    def test_timeout_on_a_later_page_does_not_refetch_completed_pages(self) -> None:
        http = _ScriptedHttp([_playlists_page("p1", "t2"), TimeoutError(), _playlists_page("p2", None)])
        mock.patch("youtube.data_api._data_client", return_value=_data_service(http)).start()

        playlists, truncated = data_api.fetch_playlists()

        self.assertEqual([p["id"] for p in playlists], ["p1", "p2"])
        self.assertFalse(truncated)
        self.assertEqual(http.requests, 3)

    def test_timeouts_on_every_attempt_raise_after_the_shared_budget(self) -> None:
        http = _ScriptedHttp([TimeoutError()] * MAX_ATTEMPTS)
        mock.patch("youtube.data_api._data_client", return_value=_data_service(http)).start()

        with self.assertRaises(TimeoutError):
            data_api.fetch_playlists()

        self.assertEqual(http.requests, MAX_ATTEMPTS)


class StageOutcomeTest(_NoWaitTestCase, IsolatedDatabaseTestCase):
    def _run(self, http: _ScriptedHttp, checkpoint: Any = analytics_api._noop_checkpoint) -> None:
        service = _analytics_service(http)

        def stage(counts: SyncCounts) -> None:
            counts.rows_fetched += 7
            counts.rows_written += 7
            analytics_api._fetch_analytics_rows(service, {"maxResults": 1}, checkpoint=checkpoint)

        orchestration._run_stage("batch-1", "video_traffic_sources", "incremental", None, stage)

    def _stored_run(self) -> SyncRun:
        run = reader.select_one(SyncRun, where=[("batch_id", "=", "batch-1")])
        assert run is not None
        return run

    def test_exhausted_timeouts_record_a_failed_stage_with_partial_counters(self) -> None:
        with self.assertLogs("youtube_analytics.sync", level="ERROR") as logs:
            with self.assertRaises(TimeoutError):
                self._run(_ScriptedHttp([TimeoutError()] * MAX_ATTEMPTS))

        run = self._stored_run()
        self.assertEqual((run.status, run.rows_fetched, run.rows_written), ("failed", 7, 7))
        self.assertIn("exception_type=TimeoutError", logs.output[0])

    def test_stop_during_a_retried_request_cancels_at_the_next_page(self) -> None:
        # Page 1 times out once, then answers a full page; the stop lands at page 2's checkpoint.
        checkpoint = mock.Mock(side_effect=status.SyncCancelled())
        http = _ScriptedHttp([TimeoutError(), _report([["2024-01-01", 5]])])

        with self.assertRaises(status.SyncCancelled):
            self._run(http, checkpoint)

        self.assertEqual(http.requests, 2)
        checkpoint.assert_called_once()
        self.assertEqual(self._stored_run().status, "cancelled")
