from __future__ import annotations

import unittest
from typing import Any
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import sync
from routes.synchronization import router


class SyncRoutesTestCase(unittest.TestCase):
    """Exercises the real HTTP contract with stage execution stubbed out.

    TestClient runs FastAPI background tasks inside the response cycle, so the queued
    plan has already been executed — and its reservation released — by the time a
    response is inspected. Assertions are written accordingly.
    """

    def setUp(self) -> None:
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app)

        sync.reset_sync_status()
        self.addCleanup(sync.reset_sync_status)

        # A plain Mock would swallow execute_plan's reservation-release contract, since
        # the route only ever calls try_begin_sync() and never a terminal transition
        # itself — the real execute_plan releases it by completing or failing. Mimic
        # that here so tests asserting the reservation clears after a successful post
        # exercise a real invariant rather than one the stub silently preserved by doing
        # nothing.
        self.execute = self._patch(
            "routes.synchronization.sync.execute_plan",
            side_effect=lambda stages: sync.complete_sync("Sync complete"),
        )
        self._patch("sync.plans.available_years", return_value=(2025, 2024, 2023))

    def _patch(self, target: str, **kwargs: Any) -> mock.Mock:
        patcher = mock.patch(target, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def _post(self, body: object) -> Any:
        """POST a plan and return the httpx response (typed Any to avoid importing httpx2)."""
        return self.client.post("/sync/trigger", json=body)

    @property
    def queued_stages(self) -> list[str]:
        return [stage.stage for stage in self.execute.call_args[0][0]]


class ValidPlanTest(SyncRoutesTestCase):
    def test_valid_plan_is_queued(self) -> None:
        response = self._post({"stages": [{"stage": "videos"}, {"stage": "fx_rates"}]})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"queued": True})
        self.execute.assert_called_once()
        self.assertEqual(self.queued_stages, ["videos", "fx_rates"])

    def test_submission_order_does_not_affect_queued_order(self) -> None:
        self._post({
            "stages": [
                {"stage": "fx_rates"},
                {"stage": "video_analytics", "scope": "all"},
                {"stage": "videos"},
            ]
        })

        self.assertEqual(self.queued_stages, ["videos", "video_analytics", "fx_rates"])

    def test_independent_periods_reach_the_executor(self) -> None:
        self._post({
            "stages": [
                {"stage": "video_analytics", "scope": "year", "year": 2024},
                {"stage": "video_traffic_sources", "scope": "incremental"},
            ]
        })

        by_stage = {stage.stage: stage for stage in self.execute.call_args[0][0]}
        self.assertEqual((by_stage["video_analytics"].scope, by_stage["video_analytics"].year),
                         ("year", 2024))
        self.assertEqual(by_stage["video_traffic_sources"].scope, "incremental")
        self.assertIsNone(by_stage["video_traffic_sources"].year)

    def test_single_stage_plan_is_accepted(self) -> None:
        response = self._post({"stages": [{"stage": "fx_rates"}]})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.queued_stages, ["fx_rates"])

    def test_pruning_with_both_prerequisites_is_queued_in_canonical_order(self) -> None:
        response = self._post({
            "stages": [{"stage": "pruning"}, {"stage": "videos"}, {"stage": "playlists"}]
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.queued_stages, ["playlists", "videos", "pruning"])

    def test_reservation_is_released_after_the_queued_plan_runs(self) -> None:
        response = self._post({"stages": [{"stage": "videos"}]})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(sync.get_sync_status()["state"], "success")


class SemanticRejectionTest(SyncRoutesTestCase):
    def _assert_rejected(self, body: object, status_code: int) -> None:
        response = self._post(body)
        self.assertEqual(response.status_code, status_code)
        self.execute.assert_not_called()
        self.assertEqual(sync.get_sync_status()["state"], "idle")

    def test_empty_stage_list_is_rejected(self) -> None:
        self._assert_rejected({"stages": []}, 400)

    def test_duplicate_stage_is_rejected(self) -> None:
        self._assert_rejected({"stages": [{"stage": "videos"}, {"stage": "videos"}]}, 400)

    def test_period_aware_stage_without_scope_is_rejected(self) -> None:
        self._assert_rejected({"stages": [{"stage": "video_analytics"}]}, 400)

    def test_year_scope_without_year_is_rejected(self) -> None:
        self._assert_rejected(
            {"stages": [{"stage": "video_analytics", "scope": "year"}]}, 400
        )

    def test_year_with_incremental_scope_is_rejected(self) -> None:
        self._assert_rejected(
            {"stages": [{"stage": "video_analytics", "scope": "incremental", "year": 2024}]}, 400
        )

    def test_scope_on_non_period_stage_is_rejected(self) -> None:
        self._assert_rejected({"stages": [{"stage": "videos", "scope": "all"}]}, 400)

    def test_pruning_without_playlists_or_videos_is_rejected(self) -> None:
        self._assert_rejected({"stages": [{"stage": "pruning"}]}, 400)

    def test_pruning_without_videos_is_rejected(self) -> None:
        self._assert_rejected({"stages": [{"stage": "pruning"}, {"stage": "playlists"}]}, 400)

    def test_pruning_with_scope_is_rejected(self) -> None:
        self._assert_rejected(
            {"stages": [
                {"stage": "pruning", "scope": "all"},
                {"stage": "playlists"},
                {"stage": "videos"},
            ]}, 400
        )

    def test_unavailable_year_is_rejected(self) -> None:
        self._assert_rejected(
            {"stages": [{"stage": "video_analytics", "scope": "year", "year": 1999}]}, 400
        )

    def test_future_year_is_rejected(self) -> None:
        self._assert_rejected(
            {"stages": [{"stage": "video_analytics", "scope": "year", "year": 2099}]}, 400
        )


class StructuralRejectionTest(SyncRoutesTestCase):
    def _assert_unprocessable(self, body: object) -> None:
        response = self._post(body)
        self.assertEqual(response.status_code, 422)
        self.execute.assert_not_called()
        self.assertEqual(sync.get_sync_status()["state"], "idle")

    def test_missing_stages_field_is_unprocessable(self) -> None:
        self._assert_unprocessable({})

    def test_unknown_stage_is_unprocessable(self) -> None:
        self._assert_unprocessable({"stages": [{"stage": "chapters"}]})

    def test_year_on_comments_is_rejected(self) -> None:
        response = self.client.post(
            "/sync/trigger", json={"stages": [{"stage": "comments", "scope": "all", "year": 2024}]}
        )
        self.assertEqual(response.status_code, 400)

    def test_unknown_scope_is_unprocessable(self) -> None:
        self._assert_unprocessable(
            {"stages": [{"stage": "video_analytics", "scope": "last_week"}]}
        )

    def test_wrong_stages_type_is_unprocessable(self) -> None:
        self._assert_unprocessable({"stages": "videos"})

    def test_non_numeric_year_is_unprocessable(self) -> None:
        self._assert_unprocessable(
            {"stages": [{"stage": "video_analytics", "scope": "year", "year": "soon"}]}
        )

    def test_unknown_top_level_field_is_unprocessable(self) -> None:
        self._assert_unprocessable({"stages": [{"stage": "videos"}], "priority": "high"})

    def test_unknown_stage_field_is_unprocessable(self) -> None:
        self._assert_unprocessable({"stages": [{"stage": "videos", "extra": True}]})


class ConflictTest(SyncRoutesTestCase):
    def test_returns_409_while_a_sync_is_active(self) -> None:
        self.assertTrue(sync.try_begin_sync("already running"))

        response = self._post({"stages": [{"stage": "videos"}]})

        self.assertEqual(response.status_code, 409)
        self.execute.assert_not_called()

    def test_active_sync_state_survives_a_rejected_request(self) -> None:
        self.assertTrue(sync.try_begin_sync("already running"))

        self._post({"stages": [{"stage": "videos"}]})

        self.assertEqual(sync.get_sync_status(), {"state": "running", "message": "already running"})


class StatusRouteTest(SyncRoutesTestCase):
    def test_status_shape_reports_the_explicit_lifecycle(self) -> None:
        response = self.client.get("/sync/status")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()), {"state", "message"})
        self.assertEqual(response.json()["state"], "idle")

    def test_status_reports_the_starting_message_before_work_begins(self) -> None:
        observed: list[dict] = []

        def fake_execute(stages: object) -> None:
            observed.append(sync.get_sync_status())
            sync.complete_sync("Sync complete")

        self.execute.side_effect = fake_execute

        self._post({"stages": [{"stage": "videos"}]})

        self.assertEqual(observed[0], {"state": "running", "message": "Starting sync..."})


class AddTaskFailureTest(SyncRoutesTestCase):
    def test_reservation_is_rolled_back_when_enqueueing_fails(self) -> None:
        self._patch("fastapi.BackgroundTasks.add_task", side_effect=RuntimeError("queue full"))

        with self.assertRaises(RuntimeError):
            self._post({"stages": [{"stage": "videos"}]})

        self.assertEqual(sync.get_sync_status(), {"state": "idle", "message": ""})
        self.execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
