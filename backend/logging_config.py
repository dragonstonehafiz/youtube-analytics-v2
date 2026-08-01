"""Shared standard-library logging configuration for backend application code.

Two fixed file destinations live beside the SQLite database under `backend/data/`:

- `application.log` — general/high-level application and sync records (INFO+).
- `sync.log` — high-level sync records plus detailed sync-only DEBUG events.

All application modules must acquire loggers through `get_logger(area)` rather than
calling `logging.getLogger()` directly, so configuration happens exactly once
regardless of which module is imported first. See `backend/README.md` and
`agent-workflows/references/architecture.md` for the routing rules this module
implements.
"""

from __future__ import annotations

import logging
import traceback
from datetime import datetime, timezone
from pathlib import Path

_BACKEND_ROOT = Path(__file__).parent
_APP_LOG_PATH = _BACKEND_ROOT / "data" / "application.log"
_SYNC_LOG_PATH = _BACKEND_ROOT / "data" / "sync.log"

_PARENT_LOGGER_NAME = "youtube_analytics"
_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"

# Area names for which a logger currently holds handlers bound to the paths in
# `_configured_paths`. Reconfiguring with different paths (tests only) rebuilds every
# logger in this set so no logger is left pointing at a closed/stale file.
_KNOWN_AREAS: set[str] = set()
_configured_paths: tuple[Path, Path] | None = None
_current_app_handler: logging.Handler | None = None
_current_sync_handler: logging.Handler | None = None


class TimezoneAwareFormatter(logging.Formatter):
    """Formatter that renders `%(asctime)s` as a UTC ISO 8601 timestamp with `+00:00`.

    `logging.Formatter`'s default `asctime` is local-time and not timezone-aware, so
    this derives the timestamp from `LogRecord.created` instead.
    """

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        """Return `record.created` as an ISO 8601 UTC timestamp with millisecond precision."""
        return datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds")


def _logger_name(area: str) -> str:
    """Return the fully qualified logger name for an application area."""
    return f"{_PARENT_LOGGER_NAME}.{area}"


def _reset_logger(name: str) -> None:
    """Detach and close every handler currently on the named logger."""
    logger = logging.getLogger(name)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


def configure_logging(app_path: Path | str | None = None, sync_path: Path | str | None = None) -> None:
    """Idempotently configure the application and sync file handlers.

    `app_path`/`sync_path` default to the fixed backend-root constants. Nothing in
    application code passes them; they exist so tests can target a `TemporaryDirectory`
    instead of a developer's real logs. Calling this repeatedly with the same resolved
    paths is a no-op — handlers are bound once and not retargeted. Calling it with
    different paths (test isolation only) rebuilds every area logger created so far
    against the new paths, closing the old handlers first so Windows does not retain
    file locks.
    """
    global _configured_paths, _current_app_handler, _current_sync_handler

    resolved_app = Path(app_path) if app_path is not None else _APP_LOG_PATH
    resolved_sync = Path(sync_path) if sync_path is not None else _SYNC_LOG_PATH

    # The sync logger holds both handlers, so a shared destination would append every
    # sync INFO+ record to that file twice. The module constants never collide; this
    # guards the explicit-path form, which only tests use.
    if resolved_app.resolve() == resolved_sync.resolve():
        raise ValueError(
            f"application and sync log paths must differ, both resolve to {resolved_app.resolve()}"
        )

    if _configured_paths == (resolved_app, resolved_sync):
        return

    resolved_app.parent.mkdir(parents=True, exist_ok=True)
    resolved_sync.parent.mkdir(parents=True, exist_ok=True)

    formatter = TimezoneAwareFormatter(_LOG_FORMAT)

    # delay=True: the file is opened on the first record, not at construction. Modules
    # call get_logger() at import scope, so without this every import of an instrumented
    # module would create the real backend/data/*.log files even in processes that never
    # log anything -- test runs and CI's `import server` check included.
    app_handler = logging.FileHandler(resolved_app, encoding="utf-8", delay=True)
    app_handler.setLevel(logging.INFO)
    app_handler.setFormatter(formatter)

    sync_handler = logging.FileHandler(resolved_sync, encoding="utf-8", delay=True)
    sync_handler.setLevel(logging.DEBUG)
    sync_handler.setFormatter(formatter)

    # Rebuild every area logger already handed out, plus the two well-known areas, so a
    # reconfiguration (test isolation only) never leaves a logger holding a handler for
    # a now-stale path.
    for area in _KNOWN_AREAS | {"lifecycle", "sync"}:
        _reset_logger(_logger_name(area))

    lifecycle_logger = logging.getLogger(_logger_name("lifecycle"))
    lifecycle_logger.setLevel(logging.INFO)
    lifecycle_logger.propagate = False
    lifecycle_logger.addHandler(app_handler)

    sync_logger = logging.getLogger(_logger_name("sync"))
    # Set on the logger itself, not only the handler: a logger left at INFO discards
    # DEBUG records before any handler is consulted.
    sync_logger.setLevel(logging.DEBUG)
    sync_logger.propagate = False
    # Sync INFO+ must reach both files; sync DEBUG must reach sync.log only. Holding
    # both handlers on this one logger is what produces that routing.
    sync_logger.addHandler(sync_handler)
    sync_logger.addHandler(app_handler)

    for area in _KNOWN_AREAS - {"lifecycle", "sync"}:
        other_logger = logging.getLogger(_logger_name(area))
        other_logger.setLevel(logging.INFO)
        other_logger.propagate = False
        other_logger.addHandler(app_handler)

    _KNOWN_AREAS.update({"lifecycle", "sync"})
    _configured_paths = (resolved_app, resolved_sync)
    _current_app_handler = app_handler
    _current_sync_handler = sync_handler


def reset_logging() -> None:
    """Detach and close every area logger's handlers, returning to an unconfigured state.

    For test teardown. Calling `configure_logging()` with no arguments would instead bind
    handlers to the real `backend/data/*.log` paths, so a test module that restored the
    default configuration that way would leave every later test in the process pointing
    at a developer's real logs. After this, the next `get_logger()` reconfigures from
    scratch.
    """
    global _configured_paths, _current_app_handler, _current_sync_handler

    for area in _KNOWN_AREAS:
        _reset_logger(_logger_name(area))
    _KNOWN_AREAS.clear()
    _configured_paths = None
    _current_app_handler = None
    _current_sync_handler = None


def get_logger(area: str) -> logging.Logger:
    """Return the configured `youtube_analytics.<area>` logger, configuring it first.

    `area` other than `"lifecycle"` or `"sync"` receives the application handler only,
    at INFO, under the same `propagate = False` rule — never a handler-less logger,
    since `propagate = False` would then discard its records silently.

    Only configures with the default paths if nothing has configured logging yet.
    Handlers are bound the first time logging is configured and are not retargeted
    afterwards, so a caller (a test) that already configured explicit paths is not
    silently reset back to the real default files by a later `get_logger()` call.
    """
    if _configured_paths is None:
        configure_logging()
    name = _logger_name(area)
    if area not in _KNOWN_AREAS:
        assert _current_app_handler is not None
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        logger.addHandler(_current_app_handler)
        _KNOWN_AREAS.add(area)
    return logging.getLogger(name)


def exception_context(exc: BaseException) -> str:
    """Return safe diagnostic context for `exc`: exception class and final frame location.

    Never includes the exception message/args, chained-exception text, local variables,
    request parameters, credentials, OAuth tokens, authorization headers, or response
    bodies — only the exception's type name and the basename/function/line of the final
    traceback frame.
    """
    frames = traceback.extract_tb(exc.__traceback__)
    if frames:
        frame = frames[-1]
        location = f"{Path(frame.filename).name}:{frame.name}:{frame.lineno}"
    else:
        location = "unknown"
    return f"exception_type={type(exc).__name__} location={location}"
