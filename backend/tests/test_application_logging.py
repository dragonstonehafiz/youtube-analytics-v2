from __future__ import annotations

import io
import logging
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import logging_config
import server
from logging_config import (
    TimezoneAwareFormatter,
    configure_logging,
    exception_context,
    get_logger,
    reset_logging,
)

_TIMESTAMP_RE = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+00:00"


class _TempLoggingMixin(unittest.TestCase):
    """Redirects the shared logging configuration to a disposable directory.

    Every test that emits real log records must use this so the suite never opens or
    appends to a developer's `backend/data/*.log`. `reset_logging` is registered as a
    cleanup *before* the TemporaryDirectory's own cleanup, so it runs first (unittest
    cleanups run in LIFO order) and releases the temp-path file handles before the
    directory is removed -- otherwise Windows would keep the files locked. Cleanup must
    not call `configure_logging()` with no arguments, which would rebind handlers to the
    real log paths instead of releasing them.
    """

    def _configure_temp_logging(self) -> tuple[Path, Path]:
        tmpdir = TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        app_path = Path(tmpdir.name) / "application.log"
        sync_path = Path(tmpdir.name) / "sync.log"
        configure_logging(app_path=app_path, sync_path=sync_path)
        self.addCleanup(reset_logging)
        return app_path, sync_path


class TimezoneAwareFormatterTest(unittest.TestCase):
    """Attaches the formatter directly to a StringIO handler.

    Deliberately does not use `assertLogs`, since it replaces/bypasses the handler under
    test rather than exercising `TimezoneAwareFormatter.formatTime`.
    """

    def setUp(self) -> None:
        self.stream = io.StringIO()
        handler = logging.StreamHandler(self.stream)
        handler.setFormatter(TimezoneAwareFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        self.logger = logging.getLogger("test.timezone_aware_formatter")
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False
        self.logger.addHandler(handler)
        self.addCleanup(self.logger.removeHandler, handler)

    def test_record_has_millisecond_utc_timestamp_level_name_and_message(self) -> None:
        self.logger.info("hello world")
        line = self.stream.getvalue().strip()

        timestamp, level, name, message = line.split(" ", 3)
        self.assertRegex(timestamp, rf"^{_TIMESTAMP_RE}$")
        self.assertEqual(level, "INFO")
        self.assertEqual(name, "test.timezone_aware_formatter")
        self.assertEqual(message, "hello world")


class DefaultPathConstantsTest(unittest.TestCase):
    """Only inspects path constants -- never calls configure_logging(), so it never
    touches a developer's real log files."""

    def test_default_paths_resolve_under_the_backend_root(self) -> None:
        backend_root = Path(logging_config.__file__).resolve().parent
        self.assertEqual(logging_config._APP_LOG_PATH, backend_root / "data" / "application.log")
        self.assertEqual(logging_config._SYNC_LOG_PATH, backend_root / "data" / "sync.log")

    def test_default_paths_are_independent_of_process_working_directory(self) -> None:
        expected_app = logging_config._APP_LOG_PATH.resolve()
        expected_sync = logging_config._SYNC_LOG_PATH.resolve()

        original_cwd = Path.cwd()
        with TemporaryDirectory() as other_dir:
            os.chdir(other_dir)
            try:
                self.assertEqual(logging_config._APP_LOG_PATH.resolve(), expected_app)
                self.assertEqual(logging_config._SYNC_LOG_PATH.resolve(), expected_sync)
            finally:
                os.chdir(original_cwd)


class ConfigureLoggingTest(_TempLoggingMixin, unittest.TestCase):
    def test_creates_parent_directory_eagerly_but_defers_the_files(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        nested = Path(tmp.name) / "nested" / "log_dir"
        app_path = nested / "application.log"
        sync_path = nested / "sync.log"

        configure_logging(app_path=app_path, sync_path=sync_path)
        self.addCleanup(reset_logging)

        # The directory is created up front so a deferred open cannot fail later, but the
        # handlers use delay=True, so configuring alone must not create the files.
        self.assertTrue(nested.is_dir())
        self.assertFalse(app_path.exists())
        self.assertFalse(sync_path.exists())

        get_logger("sync").info("first record")

        self.assertTrue(app_path.exists())
        self.assertTrue(sync_path.exists())

    def test_identical_application_and_sync_paths_are_rejected(self) -> None:
        """The sync logger holds both handlers, so a shared file would double every
        sync INFO+ record. Configuration must fail loudly rather than duplicate."""
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        same = Path(tmp.name) / "combined.log"

        with self.assertRaises(ValueError) as raised:
            configure_logging(app_path=same, sync_path=same)

        self.assertIn("must differ", str(raised.exception))

    def test_equivalent_paths_spelled_differently_are_rejected(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        direct = Path(tmp.name) / "combined.log"
        indirect = Path(tmp.name) / "." / "combined.log"

        with self.assertRaises(ValueError):
            configure_logging(app_path=direct, sync_path=indirect)

    def test_repeated_calls_with_the_same_paths_do_not_duplicate_handlers(self) -> None:
        app_path, sync_path = self._configure_temp_logging()
        configure_logging(app_path=app_path, sync_path=sync_path)
        configure_logging(app_path=app_path, sync_path=sync_path)

        get_logger("sync").info("idempotence marker")

        self.assertEqual(app_path.read_text(encoding="utf-8").count("idempotence marker"), 1)
        self.assertEqual(sync_path.read_text(encoding="utf-8").count("idempotence marker"), 1)

    def test_env_vars_do_not_override_the_resolved_paths(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        fixed_app = Path(tmp.name) / "application.log"
        fixed_sync = Path(tmp.name) / "sync.log"
        bogus_app = Path(tmp.name) / "env_should_not_be_used_app.log"
        bogus_sync = Path(tmp.name) / "env_should_not_be_used_sync.log"

        with mock.patch.object(logging_config, "_APP_LOG_PATH", fixed_app), \
                mock.patch.object(logging_config, "_SYNC_LOG_PATH", fixed_sync), \
                mock.patch.dict(os.environ, {"APP_LOG_PATH": str(bogus_app), "SYNC_LOG_PATH": str(bogus_sync)}):
            configure_logging()
            self.addCleanup(reset_logging)
            # Handlers are delay=True, so emit inside the patch to force the open.
            get_logger("sync").info("env override marker")

        self.assertTrue(fixed_app.exists())
        self.assertTrue(fixed_sync.exists())
        self.assertFalse(bogus_app.exists())
        self.assertFalse(bogus_sync.exists())


class RoutingTest(_TempLoggingMixin, unittest.TestCase):
    def setUp(self) -> None:
        self.app_path, self.sync_path = self._configure_temp_logging()

    @staticmethod
    def _content(path: Path) -> str:
        """Return the file's text, or "" if it was never opened.

        Handlers use delay=True, so a destination that received no record has no file on
        disk. For these routing assertions that is the same as empty content.
        """
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def _app_content(self) -> str:
        return self._content(self.app_path)

    def _sync_content(self) -> str:
        return self._content(self.sync_path)

    def test_lifecycle_info_reaches_application_file_only(self) -> None:
        get_logger("lifecycle").info("lifecycle info marker")

        self.assertIn("lifecycle info marker", self._app_content())
        self.assertNotIn("lifecycle info marker", self._sync_content())

    def test_sync_debug_reaches_sync_file_only(self) -> None:
        get_logger("sync").debug("sync debug marker")

        self.assertNotIn("sync debug marker", self._app_content())
        self.assertIn("sync debug marker", self._sync_content())

    def test_sync_info_and_error_reach_both_files_exactly_once(self) -> None:
        logger = get_logger("sync")
        logger.info("sync info marker")
        logger.error("sync error marker")

        self.assertEqual(self._app_content().count("sync info marker"), 1)
        self.assertEqual(self._sync_content().count("sync info marker"), 1)
        self.assertEqual(self._app_content().count("sync error marker"), 1)
        self.assertEqual(self._sync_content().count("sync error marker"), 1)

    def test_unregistered_area_gets_the_application_handler_only(self) -> None:
        get_logger("metadata").info("metadata info marker")

        self.assertIn("metadata info marker", self._app_content())
        self.assertNotIn("metadata info marker", self._sync_content())

    def test_no_handler_is_attached_to_the_shared_parent_logger(self) -> None:
        get_logger("lifecycle")
        get_logger("sync")
        get_logger("metadata")

        parent = logging.getLogger("youtube_analytics")
        self.assertEqual(parent.handlers, [])

    def test_every_area_logger_has_propagate_false(self) -> None:
        for area in ("lifecycle", "sync", "metadata"):
            self.assertFalse(get_logger(area).propagate)

    def test_sync_loggers_own_level_admits_debug(self) -> None:
        get_logger("sync").debug("debug level admission marker")

        self.assertIn("debug level admission marker", self._sync_content())

    def test_repeated_get_logger_calls_do_not_duplicate_records(self) -> None:
        get_logger("sync")
        get_logger("sync")
        get_logger("sync").info("no duplicate marker")

        self.assertEqual(self._app_content().count("no duplicate marker"), 1)
        self.assertEqual(self._sync_content().count("no duplicate marker"), 1)

    def test_records_occupy_exactly_one_physical_line_each(self) -> None:
        logger = get_logger("sync")
        for i in range(3):
            logger.info(
                "Sync stage completed sync_type=videos rows_fetched=%d rows_written=0 rows_deleted=0", i
            )

        lines = [line for line in self._sync_content().splitlines() if line.strip()]
        self.assertEqual(len(lines), 3)


class DirectImportFormattingTest(_TempLoggingMixin, unittest.TestCase):
    """`sync.orchestration` is imported directly by the existing sync tests without
    importing `server.py`; its module-level logger must still be fully configured and
    formatted through `get_logger()`."""

    def setUp(self) -> None:
        self.app_path, self.sync_path = self._configure_temp_logging()

    def test_orchestration_module_logger_produces_fully_formatted_records(self) -> None:
        from sync import orchestration

        orchestration._logger.info("direct import marker")
        orchestration._logger.error("direct import error marker")

        content = self.sync_path.read_text(encoding="utf-8")
        self.assertRegex(
            content, rf"{_TIMESTAMP_RE} INFO youtube_analytics\.sync direct import marker"
        )
        self.assertRegex(
            content, rf"{_TIMESTAMP_RE} ERROR youtube_analytics\.sync direct import error marker"
        )


class ExceptionContextTest(unittest.TestCase):
    def test_reports_type_and_location_without_message_or_args(self) -> None:
        try:
            raise RuntimeError("access_token=FAKE_OAUTH_TOKEN body={\"error\": \"quotaExceeded\"}")
        except RuntimeError as exc:
            context = exception_context(exc)

        self.assertIn("exception_type=RuntimeError", context)
        self.assertIn(os.path.basename(__file__), context)
        self.assertNotIn("FAKE_OAUTH_TOKEN", context)
        self.assertNotIn("quotaExceeded", context)
        self.assertNotIn("access_token", context)


class ExceptionContextInLogFileTest(_TempLoggingMixin, unittest.TestCase):
    def setUp(self) -> None:
        self.app_path, self.sync_path = self._configure_temp_logging()

    def test_safe_exception_context_excludes_secrets_from_both_files(self) -> None:
        logger = get_logger("sync")
        try:
            raise RuntimeError("Authorization: Bearer FAKE_OAUTH_TOKEN {\"quotaExceeded\": true}")
        except RuntimeError as exc:
            logger.error("Sync stage failed sync_type=video_analytics %s", exception_context(exc))

        for path in (self.app_path, self.sync_path):
            content = path.read_text(encoding="utf-8")
            self.assertNotIn("FAKE_OAUTH_TOKEN", content)
            self.assertNotIn("quotaExceeded", content)
            self.assertIn("exception_type=RuntimeError", content)


class LifespanTest(_TempLoggingMixin, unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.app_path, self.sync_path = self._configure_temp_logging()

    async def test_logs_one_startup_and_one_shutdown_record_in_order(self) -> None:
        calls: list[str] = []

        def record_sweep() -> int:
            calls.append("mark_incomplete_sync_runs")
            return 0

        # Every startup step is stubbed, including the stranded-run sweep — it issues a
        # real UPDATE, so leaving it unpatched would mutate the application database.
        with mock.patch("server.database.init_db", side_effect=lambda: calls.append("init_db")), \
                mock.patch("server.database.mark_incomplete_sync_runs", side_effect=record_sweep), \
                mock.patch(
                    "server.sync.start_background_scheduler",
                    side_effect=lambda: calls.append("start_background_scheduler"),
                ):
            with self.assertLogs("youtube_analytics.lifecycle", level="INFO") as captured:
                async with server.lifespan(server.app):
                    pass

        self.assertEqual(
            calls, ["init_db", "mark_incomplete_sync_runs", "start_background_scheduler"])
        messages = [record.getMessage() for record in captured.records]
        self.assertEqual(len(messages), 2)
        self.assertIn("startup", messages[0].lower())
        self.assertIn("shutdown", messages[1].lower())

    async def test_a_stranded_run_sweep_adds_one_warning_between_the_two(self) -> None:
        with mock.patch("server.database.init_db"), \
                mock.patch("server.database.mark_incomplete_sync_runs", return_value=3), \
                mock.patch("server.sync.start_background_scheduler"):
            with self.assertLogs("youtube_analytics.lifecycle", level="INFO") as captured:
                async with server.lifespan(server.app):
                    pass

        self.assertEqual(
            [record.levelname for record in captured.records], ["INFO", "WARNING", "INFO"])
        self.assertIn("count=3", captured.records[1].getMessage())

    async def test_startup_failure_is_logged_as_an_error_before_shutdown(self) -> None:
        """A failed startup must not look identical to a clean run.

        Shutdown is still emitted (teardown after a failed startup stays visible), but an
        ERROR record between the two identifies the failure.
        """
        # init_db raises before the sweep is reached, but it is stubbed anyway so that
        # reordering the startup steps can never turn this test into a real UPDATE.
        with mock.patch("server.database.init_db", side_effect=RuntimeError("boom")), \
                mock.patch("server.database.mark_incomplete_sync_runs", return_value=0), \
                mock.patch("server.sync.start_background_scheduler"):
            with self.assertLogs("youtube_analytics.lifecycle", level="INFO") as captured:
                with self.assertRaises(RuntimeError):
                    async with server.lifespan(server.app):
                        pass

        levels = [record.levelname for record in captured.records]
        messages = [record.getMessage() for record in captured.records]
        self.assertEqual(levels, ["INFO", "ERROR", "INFO"])
        self.assertIn("startup", messages[0].lower())
        self.assertIn("startup failed", messages[1].lower())
        self.assertIn("shutdown", messages[2].lower())

        # Safe context only -- the exception's own message must not be interpolated.
        self.assertIn("exception_type=RuntimeError", messages[1])
        self.assertNotIn("boom", messages[1])

    async def test_successful_startup_logs_no_error_record(self) -> None:
        # The sweep must be stubbed like every other startup step: it issues a real UPDATE,
        # so an unpatched call here would rewrite statuses in the application database.
        with mock.patch("server.database.init_db"), \
                mock.patch("server.database.mark_incomplete_sync_runs", return_value=0), \
                mock.patch("server.sync.start_background_scheduler"):
            with self.assertLogs("youtube_analytics.lifecycle", level="INFO") as captured:
                async with server.lifespan(server.app):
                    pass

        self.assertEqual([record.levelname for record in captured.records], ["INFO", "INFO"])


if __name__ == "__main__":
    unittest.main()
