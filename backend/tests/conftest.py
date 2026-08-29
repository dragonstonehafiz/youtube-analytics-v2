from __future__ import annotations

import socket
from collections.abc import Iterator
from typing import Any

import pytest

import youtube.analytics_api as analytics_api
import youtube.data_api as data_api
from youtube import auth

_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}

_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex
_real_create_connection = socket.create_connection


class ExternalAccessError(AssertionError):
    """Raised when a test attempts a real network connection or OAuth credential fetch."""


def _is_loopback(address: Any) -> bool:
    host = address[0] if isinstance(address, tuple) else address
    return host in _LOOPBACK_HOSTS


def _guarded_connect(self: socket.socket, address: Any, *args: Any, **kwargs: Any) -> Any:
    # Loopback connections stay allowed: Windows' asyncio proactor loop opens a real
    # localhost socketpair() for its self-pipe, and TestClient's in-process ASGI
    # transport can route through anyio's loopback plumbing too. Neither reaches an
    # external host, so only non-loopback addresses are treated as real network access.
    if _is_loopback(address):
        return _real_connect(self, address, *args, **kwargs)
    raise ExternalAccessError(
        "Test attempted a real network connection. Mock the client/boundary instead."
    )


def _guarded_connect_ex(self: socket.socket, address: Any, *args: Any, **kwargs: Any) -> Any:
    if _is_loopback(address):
        return _real_connect_ex(self, address, *args, **kwargs)
    raise ExternalAccessError(
        "Test attempted a real network connection. Mock the client/boundary instead."
    )


def _guarded_create_connection(address: Any, *args: Any, **kwargs: Any) -> Any:
    # socket.create_connection() resolves the host via getaddrinfo() before ever calling
    # socket.socket.connect(), so a real DNS lookup would slip past the connect()-level
    # guard above unless this entrypoint is also checked directly.
    if _is_loopback(address):
        return _real_create_connection(address, *args, **kwargs)
    raise ExternalAccessError(
        "Test attempted a real network connection. Mock the client/boundary instead."
    )


def _blocked_get_credentials() -> Any:
    raise ExternalAccessError(
        "Test attempted to obtain real OAuth credentials. Mock youtube.auth.get_credentials instead."
    )


@pytest.fixture(autouse=True)
def _block_external_access(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Fail closed on any non-loopback socket connection or OAuth credential fetch.

    A test that legitimately needs to exercise one of these boundaries should mock it
    locally (e.g. patch the specific client/function under test) rather than disabling
    this fixture, so an unmocked path still fails loudly instead of reaching the network.
    """
    monkeypatch.setattr(socket.socket, "connect", _guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", _guarded_connect_ex)
    monkeypatch.setattr(socket, "create_connection", _guarded_create_connection)
    # youtube.data_api and youtube.analytics_api each did `from .auth import
    # get_credentials`, binding their own module-level name at import time — patching
    # youtube.auth.get_credentials alone leaves those aliases pointing at the real
    # function, so every module reference must be patched independently.
    monkeypatch.setattr(auth, "get_credentials", _blocked_get_credentials)
    monkeypatch.setattr(data_api, "get_credentials", _blocked_get_credentials)
    monkeypatch.setattr(analytics_api, "get_credentials", _blocked_get_credentials)
    yield
