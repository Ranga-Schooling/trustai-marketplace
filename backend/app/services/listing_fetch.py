"""Listing URL fetch — fetches a marketplace listing page so the user
doesn't have to retype the title/description by hand.

New capability, added alongside the "URL fetch preview" decision entry in
docs/DESIGN_NOTES.md. Deliberately kept separate from the frozen
POST /analyses contract (see CLAUDE.md, SCHEMA-0): this only produces
*suggested* values for the existing ListingIn fields. The user still
reviews and submits through the unchanged endpoint — fetched content never
bypasses validation.

Security note: fetching an arbitrary user-supplied URL server-side is a
textbook SSRF vector. Guardrails here: http(s) only, the resolved IP (both
before *and* after following redirects, to blunt DNS-rebinding) must be a
public address, redirects and response size are capped, and only HTML
responses are parsed.
"""
import ipaddress
import socket
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.schemas.schemas import ListingPreviewOut

ALLOWED_SCHEMES = {"http", "https"}
MAX_BYTES = 2_000_000
TIMEOUT_SECONDS = 8.0
MAX_REDIRECTS = 3
USER_AGENT = "TrustAI-Marketplace-Fetcher/1.0"


class FetchError(Exception):
    """Raised when the URL cannot be safely or successfully fetched."""


def _assert_public_host(host: str) -> None:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise FetchError(f"Could not resolve host: {host}") from exc

    for *_rest, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if (
            not ip.is_global
            or ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
        ):
            raise FetchError("URL resolves to a non-public address")


def _extract_meta(soup: BeautifulSoup, selector: str, attr: str = "content") -> str | None:
    tag = soup.select_one(selector)
    value = tag.get(attr) if tag else None
    return value.strip() if isinstance(value, str) and value.strip() else None


def fetch_listing_preview(url: str) -> ListingPreviewOut:
    """Fetch `url` and pull best-effort title/description suggestions."""
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES or not parsed.hostname:
        raise FetchError("Only http/https URLs are supported")
    _assert_public_host(parsed.hostname)

    try:
        with httpx.Client(
            follow_redirects=True,
            max_redirects=MAX_REDIRECTS,
            timeout=TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            with client.stream("GET", url) as resp:
                resp.raise_for_status()

                final_host = urlparse(str(resp.url)).hostname
                if final_host:
                    _assert_public_host(final_host)

                content_type = resp.headers.get("content-type", "")
                if "text/html" not in content_type:
                    raise FetchError("URL did not return an HTML page")

                body = bytearray()
                for chunk in resp.iter_bytes():
                    body += chunk
                    if len(body) > MAX_BYTES:
                        break
                html = body.decode(resp.encoding or "utf-8", errors="ignore")
    except httpx.HTTPError as exc:
        raise FetchError(f"Could not fetch URL: {exc}") from exc

    soup = BeautifulSoup(html, "lxml")
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
        source=parsed.hostname,
    )
