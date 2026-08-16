"""Unit tests for the URL-fetch service (app/services/listing_fetch.py).

Unlike test_api.py's URL-preview tests (which monkeypatch
routes.fetch_listing_preview and only prove the route converts whatever
FetchError it receives into a 422), these call fetch_listing_preview()
directly and monkeypatch socket/httpx to prove the failure modes named
in the ticket -- bot-blocked, unreachable, and (PR #21 review) redirect
SSRF/DNS-rebinding, oversized-response, bad-charset, and overloaded-server
URLs -- actually raise FetchError from inside the service itself, not
just that the route happens to handle one if raised. No real network
access; consistent with the project's "no network in tests" constraint
(CLAUDE.md).
"""
import socket
import time

import httpx
import pytest

from app.services import listing_fetch
from app.services.listing_fetch import FetchError, fetch_listing_preview

URL = "https://example.com/item/1"

PUBLIC_ADDRINFO = [
    (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0)),
]
PRIVATE_ADDRINFO = [
    (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.0.0.5", 0)),
]


def _patch_public_dns(monkeypatch):
    """Most of these tests care about failures past DNS resolution --
    point getaddrinfo at a real public IP so _resolve_public_ip passes
    and execution reaches the httpx.Client mock."""
    monkeypatch.setattr(
        "app.services.listing_fetch.socket.getaddrinfo",
        lambda host, port: PUBLIC_ADDRINFO,
    )


class _FakeClient:
    """Stand-in for httpx.Client exposing the build_request/send shape
    fetch_listing_preview actually calls (not .stream(), which the
    pinned-IP fetch in _fetch_url no longer uses)."""

    def __init__(self, send):
        self._send = send

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def build_request(self, method, url, headers=None, **kwargs):
        return httpx.Request(method, url, headers=headers)

    def send(self, request, **kwargs):
        return self._send(request, **kwargs)


def _install_fake_client(monkeypatch, send):
    monkeypatch.setattr("app.services.listing_fetch.httpx.Client", lambda **kwargs: _FakeClient(send))


def test_unresolvable_host_raises_fetch_error(monkeypatch):
    """A typo'd or deleted domain -- DNS resolution itself fails."""
    def fake_getaddrinfo(host, port):
        raise socket.gaierror("Name or service not known")

    monkeypatch.setattr("app.services.listing_fetch.socket.getaddrinfo", fake_getaddrinfo)

    with pytest.raises(FetchError, match="Could not resolve host"):
        fetch_listing_preview("https://this-domain-does-not-exist.invalid/item/1")


def test_oversized_hostname_label_raises_fetch_error(monkeypatch):
    """getaddrinfo raises UnicodeError (not gaierror) for hostnames whose
    labels fail IDNA encoding -- PR #21 review comment 6."""
    def fake_getaddrinfo(host, port):
        raise UnicodeError("label too long")

    monkeypatch.setattr("app.services.listing_fetch.socket.getaddrinfo", fake_getaddrinfo)

    with pytest.raises(FetchError, match="Invalid host"):
        fetch_listing_preview(f"https://{'a' * 300}.example/item/1")


def test_connection_failure_raises_fetch_error(monkeypatch):
    """Host resolves, but the server refuses/drops the connection."""
    _patch_public_dns(monkeypatch)

    def fake_send(request, **kwargs):
        raise httpx.ConnectError("Simulated connection refused")

    _install_fake_client(monkeypatch, fake_send)

    with pytest.raises(FetchError, match="Could not fetch URL"):
        fetch_listing_preview(URL)


def test_timeout_raises_fetch_error(monkeypatch):
    """The target server never responds within the timeout budget."""
    _patch_public_dns(monkeypatch)

    def fake_send(request, **kwargs):
        raise httpx.ReadTimeout("Simulated timeout", request=request)

    _install_fake_client(monkeypatch, fake_send)

    with pytest.raises(FetchError, match="Could not fetch URL"):
        fetch_listing_preview(URL)


def test_bot_blocked_response_raises_fetch_error(monkeypatch):
    """The target site returns 403 -- a common anti-scraping response."""
    _patch_public_dns(monkeypatch)

    def fake_send(request, **kwargs):
        return httpx.Response(403, request=request)

    _install_fake_client(monkeypatch, fake_send)

    with pytest.raises(FetchError, match="Could not fetch URL"):
        fetch_listing_preview(URL)


def test_redirect_to_private_address_is_rejected(monkeypatch):
    """A 302 pointing at a private/loopback address must not be followed
    blindly -- PR #21 review comment 1 (redirect SSRF bypass). Each hop
    re-resolves and re-validates its own host rather than trusting the
    scheme/host checked on the original URL."""
    calls = {"n": 0}

    def fake_getaddrinfo(host, port):
        calls["n"] += 1
        # First hop (example.com) resolves public; the redirect target
        # resolves private, and must be rejected before any request to it.
        return PUBLIC_ADDRINFO if calls["n"] == 1 else PRIVATE_ADDRINFO

    monkeypatch.setattr("app.services.listing_fetch.socket.getaddrinfo", fake_getaddrinfo)

    def fake_send(request, **kwargs):
        return httpx.Response(
            302,
            headers={"location": "http://169.254.169.254/latest/meta-data/"},
            request=request,
        )

    _install_fake_client(monkeypatch, fake_send)

    with pytest.raises(FetchError, match="non-public address"):
        fetch_listing_preview(URL)


def test_too_many_redirects_raises_fetch_error(monkeypatch):
    """A redirect loop must not be followed forever."""
    _patch_public_dns(monkeypatch)

    def fake_send(request, **kwargs):
        return httpx.Response(302, headers={"location": str(request.url)}, request=request)

    _install_fake_client(monkeypatch, fake_send)

    with pytest.raises(FetchError, match="Too many redirects"):
        fetch_listing_preview(URL)


def test_bad_charset_raises_fetch_error(monkeypatch):
    """A page declaring a bogus charset must produce a FetchError (422),
    not an unhandled LookupError (500) -- PR #21 review comment 5."""
    _patch_public_dns(monkeypatch)

    def fake_send(request, **kwargs):
        resp = httpx.Response(
            200,
            headers={"content-type": "text/html; charset=bogus-xyz"},
            content=b"<html></html>",
            request=request,
        )
        resp.encoding = "bogus-xyz"
        return resp

    _install_fake_client(monkeypatch, fake_send)

    with pytest.raises(FetchError, match="Could not decode page"):
        fetch_listing_preview(URL)


def test_long_hostname_is_truncated_in_source(monkeypatch):
    """ListingPreviewOut.source must respect the same 120-char cap as
    ListingIn.source (schemas.py) -- PR #21 review comment 4."""
    _patch_public_dns(monkeypatch)

    def fake_send(request, **kwargs):
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=b"<html><head><title>t</title></head></html>",
            request=request,
        )

    _install_fake_client(monkeypatch, fake_send)

    long_host = ("sub." * 40) + "example.com"
    result = fetch_listing_preview(f"https://{long_host}/item/1")

    assert result.source is not None
    assert len(result.source) <= 120


def test_slow_trickle_is_bounded_by_total_deadline(monkeypatch):
    """A server that dribbles a byte at a time must not hold the worker
    far past TIMEOUT_SECONDS -- PR #21 review comment 7. httpx's own read
    timeout is inter-chunk (resets after every byte), so a trickle never
    trips it on its own; this exercises the explicit elapsed-time check
    in the streaming loop, which is what actually bounds the total."""
    _patch_public_dns(monkeypatch)
    monkeypatch.setattr(listing_fetch, "TIMEOUT_SECONDS", 0.3)

    def trickling_iter_bytes():
        while True:
            time.sleep(0.05)
            yield b"x"

    def fake_send(request, **kwargs):
        resp = httpx.Response(200, headers={"content-type": "text/html"}, request=request)
        resp.iter_bytes = trickling_iter_bytes
        return resp

    _install_fake_client(monkeypatch, fake_send)

    start = time.monotonic()
    with pytest.raises(FetchError, match="timed out"):
        fetch_listing_preview(URL)
    elapsed = time.monotonic() - start

    # Bounded near the (patched) total budget -- not free to keep running
    # as long as bytes keep trickling in.
    assert elapsed < 1.0


def test_concurrent_fetch_limit_rejects_extra_requests(monkeypatch):
    """A burst beyond MAX_CONCURRENT_FETCHES must fail fast with a
    FetchError instead of queuing indefinitely on the threadpool --
    PR #21 review comment 7."""
    for _ in range(listing_fetch.MAX_CONCURRENT_FETCHES):
        assert listing_fetch._fetch_slots.acquire(blocking=False)

    try:
        with pytest.raises(FetchError, match="Too many URL fetches"):
            fetch_listing_preview(URL)
    finally:
        for _ in range(listing_fetch.MAX_CONCURRENT_FETCHES):
            listing_fetch._fetch_slots.release()
