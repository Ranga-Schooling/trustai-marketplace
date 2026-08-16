"""Unit tests for app/services/listing_parser.py.

Unlike test_api.py's two preview tests (which monkeypatch
listing_parser._fetch_html and only prove the route/happy-path shape),
these exercise the actual extraction and SSRF-mitigation logic directly --
the failure modes named in PR #45's review (redirect SSRF bypass,
DNS-rebinding, streaming size cap, httpx-error wrapping, contextual price
selection, safe currency fallback, title truncation). No real network
access; consistent with the project's "no network in tests" constraint
(CLAUDE.md).
"""
import socket

import httpx
import pytest

from app.services.listing_parser import (
    TITLE_MAX_LENGTH,
    _extract_price,
    _fetch_html,
    _preview_from_text,
)

URL = "https://example.com/item/1"

PUBLIC_ADDRINFO = [
    (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0)),
]
PRIVATE_ADDRINFO = [
    (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.0.0.5", 0)),
]


def _patch_public_dns(monkeypatch):
    monkeypatch.setattr(
        "app.services.listing_parser.socket.getaddrinfo",
        lambda host, port: PUBLIC_ADDRINFO,
    )


class _FakeClient:
    """Stand-in for httpx.Client exposing the build_request/send shape
    _fetch_url actually calls (not a non-streaming .get())."""

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
    monkeypatch.setattr("app.services.listing_parser.httpx.Client", lambda **kwargs: _FakeClient(send))


# ---------- SSRF / redirect handling (review comment 1) ----------

def test_unresolvable_host_raises_valueerror(monkeypatch):
    def fake_getaddrinfo(host, port):
        raise socket.gaierror("Name or service not known")

    monkeypatch.setattr("app.services.listing_parser.socket.getaddrinfo", fake_getaddrinfo)

    with pytest.raises(ValueError, match="Could not resolve host"):
        _fetch_html("https://this-domain-does-not-exist.invalid/item/1")


def test_redirect_to_private_address_is_rejected(monkeypatch):
    """A 3xx pointing at a private/loopback address must not be followed
    blindly -- the original bug: follow_redirects=True let httpx complete
    the whole redirect chain before any host was re-checked."""
    calls = {"n": 0}

    def fake_getaddrinfo(host, port):
        calls["n"] += 1
        # First hop (example.com) resolves public; the redirect target
        # resolves private and must be rejected before being fetched.
        return PUBLIC_ADDRINFO if calls["n"] == 1 else PRIVATE_ADDRINFO

    monkeypatch.setattr("app.services.listing_parser.socket.getaddrinfo", fake_getaddrinfo)

    def fake_send(request, **kwargs):
        return httpx.Response(
            302,
            headers={"location": "http://169.254.169.254/latest/meta-data/"},
            request=request,
        )

    _install_fake_client(monkeypatch, fake_send)

    with pytest.raises(ValueError, match="private or restricted address"):
        _fetch_html(URL)


def test_too_many_redirects_raises_valueerror(monkeypatch):
    _patch_public_dns(monkeypatch)

    def fake_send(request, **kwargs):
        return httpx.Response(302, headers={"location": str(request.url)}, request=request)

    _install_fake_client(monkeypatch, fake_send)

    with pytest.raises(ValueError, match="Too many redirects"):
        _fetch_html(URL)


# ---------- httpx exceptions must not escape as 500s (review comment 3) ----------

def test_connection_failure_wrapped_as_valueerror(monkeypatch):
    _patch_public_dns(monkeypatch)

    def fake_send(request, **kwargs):
        raise httpx.ConnectError("Simulated connection refused")

    _install_fake_client(monkeypatch, fake_send)

    with pytest.raises(ValueError, match="Could not fetch URL"):
        _fetch_html(URL)


def test_timeout_wrapped_as_valueerror(monkeypatch):
    _patch_public_dns(monkeypatch)

    def fake_send(request, **kwargs):
        raise httpx.ReadTimeout("Simulated timeout", request=request)

    _install_fake_client(monkeypatch, fake_send)

    with pytest.raises(ValueError, match="Could not fetch URL"):
        _fetch_html(URL)


def test_dead_link_http_status_error_wrapped_as_valueerror(monkeypatch):
    """A 404/410 dead link raises HTTPStatusError from raise_for_status(),
    which must not surface as an unhandled 500."""
    _patch_public_dns(monkeypatch)

    def fake_send(request, **kwargs):
        return httpx.Response(404, request=request)

    _install_fake_client(monkeypatch, fake_send)

    with pytest.raises(ValueError, match="Could not fetch URL"):
        _fetch_html(URL)


# ---------- streaming size cap, not post-download (review comment 4) ----------

def test_oversized_response_is_rejected_without_full_download(monkeypatch):
    """The cap must trip while streaming, not after the whole body has
    already been buffered -- proven here by an effectively-endless
    generator that would hang/OOM if fully consumed before the check ran."""
    _patch_public_dns(monkeypatch)
    chunk = b"x" * 1024

    def endless_chunks():
        while True:
            yield chunk

    def fake_send(request, **kwargs):
        resp = httpx.Response(200, headers={"content-type": "text/html"}, request=request)
        resp.iter_bytes = endless_chunks
        return resp

    _install_fake_client(monkeypatch, fake_send)

    with pytest.raises(ValueError, match="too large"):
        _fetch_html(URL)


# ---------- contextual price selection (review comment 5) ----------

def test_price_extraction_prefers_earliest_mention_over_pattern_order():
    """The exact failure scenario from the review: an incidental $-fee
    mentioned after the real R-prefixed price must not win just because
    the $-symbol pattern happens to be tried first."""
    text = "Item price: R1800, firm. Note: $5 handling fee, no PayPal."
    price, currency = _extract_price(text)
    assert (price, currency) == (1800.0, "ZAR")


def test_price_extraction_ignores_zero_or_negative_amounts():
    price, currency = _extract_price("Free giveaway, $0 shipping included.")
    assert (price, currency) == (None, None)


# ---------- currency scope fails safe, not with a wrong guess (comment 10) ----------

def test_unrecognized_currency_returns_no_price_no_wrong_guess():
    """JPY isn't in the closed symbol/code set (best-effort/lossy by team
    decision) -- it must come back as (None, None), never a mismatched
    price paired with the wrong currency."""
    price, currency = _extract_price("Selling for 5000 JPY, firm.")
    assert (price, currency) == (None, None)


# ---------- output stays ListingIn-compatible (review comment 7) ----------

def test_long_title_is_truncated_to_listingin_limit():
    text = ("a" * (TITLE_MAX_LENGTH + 50)) + "\nrest of the description here"
    preview = _preview_from_text(text)
    assert len(preview.title) == TITLE_MAX_LENGTH
