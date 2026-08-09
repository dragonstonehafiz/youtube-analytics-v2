from __future__ import annotations

from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

_BACKEND_ROOT = Path(__file__).parent.parent
_SECRETS_DIR = _BACKEND_ROOT / "secrets"
_TOKEN_PATH = _SECRETS_DIR / "token.json"
_CLIENT_SECRET_PATH = _SECRETS_DIR / "client_secret.json"

# The authoritative scope list. `SCOPES` in `.env`/`.env.example` documents the same set
# but is not read by any code, exactly like the paths beside it — there is no settings
# layer, so changing scopes means changing this list.
#
# `youtube.force-ssl` is what `commentThreads.list` requires; `youtube.readonly` alone is
# rejected with `insufficientPermissions`. It is the narrowest scope Google offers that
# grants comment reads, even though it also permits writes the app never makes — every
# comment path is read-only (see `sync.md`).
_SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/yt-analytics-monetary.readonly",
]


def get_credentials() -> Credentials:
    """Return OAuth credentials, refreshing or running the auth flow as needed."""
    creds: Credentials | None = None
    if _TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(_TOKEN_PATH), _SCOPES)

    if not creds or not creds.valid or not creds.has_scopes(_SCOPES):
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                _TOKEN_PATH.unlink(missing_ok=True)
                creds = None

        if not creds or not creds.valid:
            flow = InstalledAppFlow.from_client_secrets_file(str(_CLIENT_SECRET_PATH), _SCOPES)
            creds = flow.run_local_server(port=0, access_type="offline", include_granted_scopes="true", prompt="consent")

        _TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        _TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")

    return creds
