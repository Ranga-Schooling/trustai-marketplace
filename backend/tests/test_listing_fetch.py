"""Unit tests for the URL-fetch service (app/services/listing_fetch.py).

Unlike test_api.py's URL-preview tests (which monkeypatch
routes.fetch_listing_preview and only prove the route converts whatever
FetchError it receives into a 422), these call fetch_listing_preview()
directly and monkeypatch socket/httpx to prove the failure modes named
in the ticket -- bot-blocked and unreachable URLs -- actually raise
FetchError from inside the service itself, not just that the route
happens to handle one if raised. No real network access; consistent
with the project's "no network in tests" constraint (CLAUDE.md).
"""
import socket

import httpx
import pytest

from app.services.listing_fetch import FetchError, fetch_listing_preview

URL = "https://example.com/item/1"

PUBLIC_ADDRINFO = [
    (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0)),
]


def _patch_public_dns(monkeypatch):
    """Most of these tests care about failures past DNS resolution --
    point getaddrinfo at a real public IP so _assert_public_host passes
    and execution reaches the httpx.Client mock."""
    monkeypatch.setattr(
        "app.services.listing_fetch.socket.getaddrinfo",
        lambda host, port: PUBLIC_ADDRINFO,
    )


def test_unresolvable_host_raises_fetch_error(monkeypatch):
    """A typo'd or deleted domain -- DNS resolution itself fails."""
    def fake_getaddrinfo(host, port):
        raise socket.gaierror("Name or service not known")

    monkeypatch.setattr("app.services.listing_fetch.socket.getaddrinfo", fake_getaddrinfo)

    with pytest.raises(FetchError, match="Could not resolve host"):
        fetch_listing_preview("https://this-domain-does-not-exist.invalid/item/1")


def test_connection_failure_raises_fetch_error(monkeypatch):
    """Host resolves, but the server refuses/drops the connection."""
    _patch_public_dns(monkeypatch)

    class RefusingClient:
        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def stream(self, method, url):
            raise httpx.ConnectError("Simulated connection refused")

    monkeypatch.setattr(
        "app.services.listing_fetch.httpx.Client",
        lambda **kwargs: RefusingClient(),
    )

    with pytest.raises(FetchError, match="Could not fetch URL"):
        fetch_listing_preview(URL)


def test_timeout_raises_fetch_error(monkeypatch):
    """The target server never responds within the timeout budget."""
    _patch_public_dns(monkeypatch)

    class TimingOutClient:
        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def stream(self, method, url):
            raise httpx.ReadTimeout("Simulated timeout", request=httpx.Request("GET", url))

    monkeypatch.setattr(
        "app.services.listing_fetch.httpx.Client",
        lambda **kwargs: TimingOutClient(),
    )

    with pytest.raises(FetchError, match="Could not fetch URL"):
        fetch_listing_preview(URL)


def test_bot_blocked_response_raises_fetch_error(monkeypatch):
    """The target site returns 403 -- a common anti-scraping response."""
    _patch_public_dns(monkeypatch)

    forbidden = httpx.Response(403, request=httpx.Request("GET", URL))

    class ForbiddenStream:
        def __enter__(self):
            return forbidden

        def __exit__(self, *exc_info):
            return False

    class BlockingClient:
        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def stream(self, method, url):
            return ForbiddenStream()

    monkeypatch.setattr(
        "app.services.listing_fetch.httpx.Client",
        lambda **kwargs: BlockingClient(),
    )

    with pytest.raises(FetchError, match="Could not fetch URL"):
        fetch_listing_preview(URL)
