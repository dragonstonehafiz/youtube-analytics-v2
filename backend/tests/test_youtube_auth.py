from __future__ import annotations

import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from youtube import auth

# Captured before each test's autouse `_block_external_access` fixture (conftest.py)
# replaces `auth.get_credentials` with a stub that raises on any call — these tests
# exist specifically to exercise the real implementation's locking, with every real
# network/OAuth boundary inside it mocked locally instead.
_real_get_credentials = auth.get_credentials


class ConcurrentCredentialsTest(unittest.TestCase):
    """Two Analytics API workers can each call get_credentials() at the same moment.

    Mocks credential expiry/refresh and google_auth_oauthlib entirely — no real network
    or OAuth interaction — and asserts the read/refresh/write sequence never overlaps.
    """

    def setUp(self) -> None:
        tmpdir = TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        self.token_path = Path(tmpdir.name) / "token.json"
        self.token_path.write_text("{}", encoding="utf-8")

    def test_concurrent_callers_never_overlap_the_refresh_write_sequence(self) -> None:
        activity = {"active": 0, "max_active": 0}
        activity_lock = threading.Lock()

        creds = mock.Mock()
        creds.valid = False
        creds.expired = True
        creds.refresh_token = "refresh-token"
        creds.has_scopes.return_value = True
        creds.to_json.return_value = '{"token": "abc"}'

        def fake_refresh(request: object) -> None:
            with activity_lock:
                activity["active"] += 1
                activity["max_active"] = max(activity["max_active"], activity["active"])
            time.sleep(0.05)  # hold the section long enough to expose an unguarded race
            creds.valid = True
            with activity_lock:
                activity["active"] -= 1

        creds.refresh.side_effect = fake_refresh

        errors: list[BaseException] = []
        barrier = threading.Barrier(2)

        def call() -> None:
            try:
                barrier.wait(timeout=5)
                _real_get_credentials()
            except BaseException as exc:  # noqa: BLE001 - surfaced via assertion below
                errors.append(exc)

        with mock.patch.object(auth, "_TOKEN_PATH", self.token_path), \
                mock.patch.object(auth.Credentials, "from_authorized_user_file", return_value=creds), \
                mock.patch.object(auth, "Request"):
            threads = [threading.Thread(target=call) for _ in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10)

        self.assertEqual(errors, [])
        # Exactly one caller reaches the expired/refresh branch; the lock makes the
        # second one observe the already-refreshed, valid credentials instead of racing.
        self.assertEqual(activity["max_active"], 1)
        self.assertEqual(creds.refresh.call_count, 1)

    def test_a_failed_refresh_still_releases_the_lock_for_the_next_caller(self) -> None:
        """A refresh failure deletes the token and falls through to re-auth; the lock
        must not be left held for the other worker's call."""
        creds = mock.Mock()
        creds.valid = False
        creds.expired = True
        creds.refresh_token = "refresh-token"
        creds.has_scopes.return_value = True
        creds.refresh.side_effect = RuntimeError("invalid_grant")

        flow = mock.Mock()
        reauthed = mock.Mock()
        reauthed.to_json.return_value = '{"token": "new"}'
        flow.run_local_server.return_value = reauthed

        with mock.patch.object(auth, "_TOKEN_PATH", self.token_path), \
                mock.patch.object(auth.Credentials, "from_authorized_user_file", return_value=creds), \
                mock.patch.object(auth, "Request"), \
                mock.patch.object(auth.InstalledAppFlow, "from_client_secrets_file", return_value=flow):
            result = _real_get_credentials()

        self.assertIs(result, reauthed)
        self.assertTrue(auth._credentials_lock.acquire(timeout=1))
        auth._credentials_lock.release()


if __name__ == "__main__":
    unittest.main()
