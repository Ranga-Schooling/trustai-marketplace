"""Listing URL fetch — fetches a marketplace listing page so the user
doesn't have to retype the title/description by hand.

New capability, added alongside the "URL fetch preview" decision entry in
docs/DESIGN_NOTES.md. Deliberately kept separate from the frozen
POST /analyses contract (see CLAUDE.md, SCHEMA-0): this only produces
*suggested* values for the existing ListingIn fields. The user still
reviews and submits through the unchanged endpoint — fetched content never
bypasses validation.

Security note: fetching an arbitrary user-supplied URL server-side is a
textbook SSRF vector. Guardrails here: http(s) only, each hop resolves to
one already-validated public IP and the connection is pinned to that exact
address (see `_fetch_url` for why letting httpx do its own DNS lookup
isn't safe), redirects are followed manually and re-validated hop by hop
up to MAX_REDIRECTS, the whole operation is bounded by a single wall-clock
deadline, only a bounded number of fetches run at once, response size is
capped, and only HTML responses are parsed. This is a best-effort
mitigation appropriate to a capstone project, not an exhaustive SSRF
defense.
"""
import ipaddress
import socket
import threading
import time
from contextlib import closing
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.schemas.schemas import ListingPreviewOut

ALLOWED_SCHEMES = {"http", "https"}
MAX_BYTES = 2_000_000
TIMEOUT_SECONDS = 8.0  # total wall-clock budget for the whole fetch, not per hop
# httpx's own "read" timeout is inter-chunk, not total -- it resets after
# every byte received, so a server trickling data just under it can hold a
# connection open indefinitely without ever tripping it. Capping it small
# and fixed (independent of the remaining overall budget) means any single
# stall longer than this trips httpx's own timeout immediately; combined
# with the explicit deadline check in fetch_listing_preview, that bounds
# the worst-case overrun past TIMEOUT_SECONDS to about this many seconds,
# not up to another full TIMEOUT_SECONDS.
READ_CHUNK_TIMEOUT_SECONDS = 2.0
MAX_REDIRECTS = 3
MAX_CONCURRENT_FETCHES = 4
USER_AGENT = "TrustAI-Marketplace-Fetcher/1.0"
SOURCE_MAX_LENGTH = 120  # must match ListingIn.source (schemas.py)

_fetch_slots = threading.Semaphore(MAX_CONCURRENT_FETCHES)


class FetchError(Exception):
    """Raised when the URL cannot be safely or successfully fetched."""


def _resolve_public_ip(host: str) -> str:
    """Resolve `host` and return one public IP for the caller to connect
    to directly.

    Resolving via one lookup and connecting to that literal address (see
    `_fetch_url`) — rather than validating a hostname and then letting
    httpx resolve and connect to that same hostname itself — closes a
    DNS-rebinding window: an attacker's nameserver could otherwise return
    a public IP for this check and a private/loopback IP moments later
    when httpx does its own lookup to connect.
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise FetchError(f"Could not resolve host: {host}") from exc
    except UnicodeError as exc:
        # Hostnames with oversized/invalid labels fail IDNA encoding
        # inside getaddrinfo itself, before any lookup happens.
        raise FetchError(f"Invalid host: {host}") from exc

    for *_rest, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if (
            ip.is_global
            and not ip.is_private
            and not ip.is_loopback
            and not ip.is_link_local
            and not ip.is_multicast
            and not ip.is_reserved
        ):
            return sockaddr[0]

    raise FetchError("URL resolves to a non-public address")


def _extract_meta(soup: BeautifulSoup, selector: str, attr: str = "content") -> str | None:
    tag = soup.select_one(selector)
    value = tag.get(attr) if tag else None
    return value.strip() if isinstance(value, str) and value.strip() else None


def _fetch_url(client: httpx.Client, url: str, deadline: float) -> httpx.Response:
    """Fetch a single hop of `url`, connecting to a freshly-resolved,
    validated IP rather than the hostname, without following redirects —
    the caller re-validates and re-resolves each hop itself."""
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES or not parsed.hostname:
        raise FetchError("Only http/https URLs are supported")

    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise FetchError("Could not fetch URL: timed out")

    ip = _resolve_public_ip(parsed.hostname)
    pinned_host = f"[{ip}]" if ":" in ip else ip  # bracket IPv6 literals
    pinned_netloc = f"{pinned_host}:{parsed.port}" if parsed.port else pinned_host
    pinned_url = parsed._replace(netloc=pinned_netloc).geturl()

    # `read` capped separately (see READ_CHUNK_TIMEOUT_SECONDS) so a slow
    # trickle can't ride the full remaining budget on every single chunk.
    timeout = httpx.Timeout(remaining, read=min(remaining, READ_CHUNK_TIMEOUT_SECONDS))
    request = client.build_request("GET", pinned_url, headers={"Host": parsed.hostname}, timeout=timeout)
    # Keep TLS certificate validation (and origin-side virtual-host
    # routing) working against the real hostname even though we connect
    # to its IP literal.
    request.extensions["sni_hostname"] = parsed.hostname

    return client.send(request, stream=True, follow_redirects=False)


def fetch_listing_preview(url: str) -> ListingPreviewOut:
    """Fetch `url` and pull best-effort title/description suggestions."""
    if not _fetch_slots.acquire(blocking=False):
        raise FetchError("Too many URL fetches in progress, try again shortly")

    try:
        deadline = time.monotonic() + TIMEOUT_SECONDS
        original_hostname = urlparse(url).hostname or ""
        next_url = url

        try:
            with httpx.Client(headers={"User-Agent": USER_AGENT}) as client:
                for _ in range(MAX_REDIRECTS + 1):
                    resp = _fetch_url(client, next_url, deadline)
                    with closing(resp):
                        if resp.is_redirect:
                            location = resp.headers.get("location")
                            if not location:
                                raise FetchError("Could not fetch URL: redirect missing Location")
                            next_url = urljoin(next_url, location)
                            continue

                        resp.raise_for_status()

                        content_type = resp.headers.get("content-type", "")
                        if "text/html" not in content_type:
                            raise FetchError("URL did not return an HTML page")

                        body = bytearray()
                        for chunk in resp.iter_bytes():
                            body += chunk
                            if len(body) > MAX_BYTES:
                                break
                            if time.monotonic() > deadline:
                                raise FetchError("Could not fetch URL: timed out")

                        try:
                            html = body.decode(resp.encoding or "utf-8", errors="ignore")
                        except LookupError as exc:
                            raise FetchError(f"Could not decode page: {exc}") from exc
                    break
                else:
                    raise FetchError("Too many redirects")
        except httpx.HTTPError as exc:
            raise FetchError(f"Could not fetch URL: {exc}") from exc

        try:
            soup = BeautifulSoup(html, "lxml")
        except Exception as exc:
            raise FetchError(f"Could not parse page: {exc}") from exc

        title = (
            _extract_meta(soup, "meta[property='og:title']")
            or (soup.title.get_text(strip=True) if soup.title else None)
            or ""
        )
        description = (
            _extract_meta(soup, "meta[property='og:description']")
            or _extract_meta(soup, "meta[name='description']")
            or ""
        )

        return ListingPreviewOut(
            url=url,
            title=title[:255],
            description=description,
            source=original_hostname[:SOURCE_MAX_LENGTH] if original_hostname else None,
        )
    finally:
        _fetch_slots.release()
