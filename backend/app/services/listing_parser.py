"""Listing preview -- best-effort title/price/currency/description/seller
extraction from either pasted text or a fetched URL, so a user doesn't have
to fill in POST /analyses fields by hand (US-2.3). Additive to SCHEMA-0
(ListingPreviewIn/Out, docs/DESIGN_NOTES.md): the user still reviews and
submits through the unchanged, frozen POST /analyses -- nothing extracted
here bypasses that validation.

Security note: fetching an arbitrary user-supplied URL server-side is a
textbook SSRF vector. See _fetch_html for the mitigation.
"""
import html
import ipaddress
import re
import socket
import time
from contextlib import closing
from html import unescape
from urllib.parse import urljoin, urlparse

import httpx

from app.schemas.schemas import ListingPreviewOut

# Currency detection is a closed, best-effort set (symbols + the handful of
# codes MockProvider's own PRICE_THRESHOLDS already knows about) -- not a
# whitelist in the ListingIn.currency sense (that field validates shape,
# not membership, on purpose, see CLAUDE.md). A currency outside this set
# (JPY, AUD, INR, NGN, CHF, ...) simply fails to match any PRICE_PATTERNS
# entry, so both price and currency come back None rather than a wrong
# guess -- this is a scoping limitation of the preview's extraction, not a
# restriction on what a listing may actually use (PR #45 review, comment
# 10; left as best-effort/lossy per team decision rather than broadened).
PRICE_SYMBOL_MAP = {
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "R": "ZAR",
}

PRICE_PATTERNS = [
    r"(?P<symbol>[$€£])\s*(?P<number>\d{1,3}(?:[\,\d]*)(?:\.\d+)?)",
    r"\b(?P<number>\d{1,3}(?:[\,\d]*)(?:\.\d+)?)\s*(?P<code>USD|EUR|GBP|CAD|ZAR)\b",
    r"\b(?P<code>USD|EUR|GBP|CAD|ZAR)\s*(?P<number>\d{1,3}(?:[\,\d]*)(?:\.\d+)?)\b",
    # Tagged as `symbol` (not a bare literal) so it resolves through
    # PRICE_SYMBOL_MAP like the $/€/£ pattern above -- previously this had
    # no named group backing a currency at all, so an R-prefixed price
    # always came back with currency=None even once matched (found while
    # writing the regression test for review comment 5).
    r"\b(?P<symbol>R)(?P<number>\d{1,3}(?:[\,\d]*)(?:\.\d+)?)\b",
]

CONTACT_PATTERNS = [
    r"\b(?:whatsapp|telegram|signal|text me|sms|phone|call me|contact me)\b",
    r"\b(?:gift card|wire transfer|bitcoin|crypto|cryptocurrency|bank transfer|paypal)\b",
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    r"\+?\d[\d\s().-]{7,}\d",
]

HTML_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
HTML_META_DESC_RE = re.compile(r"<meta\s+[^>]*name=[\"']description[\"'][^>]*content=[\"'](.*?)[\"'][^>]*>", re.I | re.S)
HTML_HEADING_RE = re.compile(r"<(h[1-3])[^>]*>(.*?)</\1>", re.I | re.S)
HTML_PARAGRAPH_RE = re.compile(r"<p[^>]*>(.*?)</p>", re.I | re.S)

ALLOWED_SCHEMES = {"http", "https"}
MAX_FETCH_SIZE = 200_000
FETCH_TIMEOUT_SECONDS = 10.0  # total wall-clock budget for the whole fetch, not per hop
# httpx's own "read" timeout is inter-chunk, not total -- capped separately
# and small so a slow trickle can't ride the full remaining budget forever
# (same reasoning as READ_CHUNK_TIMEOUT_SECONDS in services/listing_fetch.py).
READ_CHUNK_TIMEOUT_SECONDS = 2.0
MAX_REDIRECTS = 3
USER_AGENT = "TrustAI Marketplace URL Preview"

# Must match ListingIn.title's max_length (schemas.py) -- a preview
# suggestion that can't fit the field it's suggesting a value for isn't
# useful (PR #45 review, comment 7).
TITLE_MAX_LENGTH = 255


def _clean_html_text(html_text: str) -> str:
    html_text = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\1>", " ", html_text)
    html_text = re.sub(r"(?s)<[^>]+>", " ", html_text)
    html_text = html.unescape(html_text)
    lines = [line.strip() for line in html_text.splitlines() if line.strip()]
    return "\n".join(lines)


def _collect_candidate_text(html_text: str) -> str:
    paragraph_matches = HTML_PARAGRAPH_RE.findall(html_text)
    if paragraph_matches:
        paragraphs = [re.sub(r"<[^>]+>", " ", p).strip() for p in paragraph_matches]
        paragraphs = [p for p in paragraphs if len(p) >= 40]
        if paragraphs:
            return "\n\n".join(paragraphs[:3])

    text = _clean_html_text(html_text)
    return text[:10_000]


def _extract_title(html_text: str, cleaned_text: str) -> str | None:
    title_match = HTML_TITLE_RE.search(html_text)
    if title_match:
        title = unescape(title_match.group(1)).strip()
        if title:
            return re.sub(r"\s+", " ", title)

    heading_match = HTML_HEADING_RE.search(html_text)
    if heading_match:
        heading = re.sub(r"<[^>]+>", " ", heading_match.group(2)).strip()
        if heading:
            return re.sub(r"\s+", " ", heading)

    first_line = cleaned_text.splitlines()[0] if cleaned_text else ""
    return first_line or None


def _extract_description(html_text: str, cleaned_text: str) -> str:
    meta_match = HTML_META_DESC_RE.search(html_text)
    if meta_match:
        description = unescape(meta_match.group(1)).strip()
        if description:
            return re.sub(r"\s+", " ", description)

    return _collect_candidate_text(html_text)


def _extract_price(text: str) -> tuple[float | None, str | None]:
    """Return the price/currency that most likely describes the listing
    itself, not just whichever PRICE_PATTERNS entry happens to be tried
    first. Every pattern is scanned across the whole text and the match
    starting *earliest* wins, regardless of which pattern found it --
    sellers state the listing price up front; incidental amounts (a
    handling fee, a deposit mentioned in passing) tend to come later in
    the text (PR #45 review, comment 5). A price of 0 or less isn't a
    usable signal (ListingIn.price requires gt=0), so it's treated as no
    match rather than passed through (comment 7).
    """
    normalized = text.replace(" ", " ")
    best: tuple[int, float, str | None] | None = None  # (start, amount, currency)
    for pat in PRICE_PATTERNS:
        for match in re.finditer(pat, normalized, re.I):
            number = match.groupdict().get("number")
            if not number:
                continue
            number = number.replace(",", "")
            try:
                amount = float(number)
            except ValueError:
                continue
            if amount <= 0:
                continue
            if match.groupdict().get("code"):
                currency = match.groupdict()["code"].upper()
            elif match.groupdict().get("symbol"):
                currency = PRICE_SYMBOL_MAP.get(match.groupdict()["symbol"])
            else:
                currency = None
            if best is None or match.start() < best[0]:
                best = (match.start(), amount, currency)
    if best is None:
        return None, None
    return best[1], best[2]


def _extract_seller_details(text: str) -> str | None:
    details = []
    contact_regex = re.compile(r"\b(whatsapp|telegram|signal|text me|sms|phone|call me|contact me)\b", re.I)
    matches = [m.group(1) for m in contact_regex.finditer(text)]
    if matches:
        unique_terms = []
        seen = set()
        for term in matches:
            normalized_term = term.lower()
            if normalized_term not in seen:
                seen.add(normalized_term)
                unique_terms.append(term)
        details.append(
            "Off-platform contact instructions: " + ", ".join(unique_terms)
        )
    if re.search(r"\b(?:gift card|wire transfer|bitcoin|crypto|cryptocurrency|bank transfer|paypal)\b", text, re.I):
        details.append("Mentions off-platform payment methods")

    emails = re.findall(CONTACT_PATTERNS[2], text)
    if emails:
        details.append(f"Email contact: {emails[0]}")

    phones = re.findall(CONTACT_PATTERNS[3], text)
    if phones:
        details.append(f"Phone contact: {phones[0].strip()}")

    if details:
        return "; ".join(details)
    return None


def _build_preview(
    title: str | None,
    price: float | None,
    currency: str | None,
    description: str | None,
    seller_details: str | None,
) -> ListingPreviewOut:
    """Single construction point for ListingPreviewOut so every extraction
    path applies the same ListingIn-alignment clamp: a suggestion that
    ListingIn would reject outright (an over-255-char title) is truncated
    rather than passed through as-is, which is the obvious next step for
    this feature (PR #45 review, comment 7). price/currency are already
    constrained by _extract_price; ListingPreviewOut itself stays
    unconstrained (no Field validation) so a stray over-length extraction
    degrades to a truncated suggestion, not a 500 from a response that
    fails its own response_model.
    """
    if title is not None:
        title = title[:TITLE_MAX_LENGTH]
    return ListingPreviewOut(
        title=title,
        price=price,
        currency=currency,
        description=description,
        seller_details=seller_details,
    )


def _preview_from_text(text: str) -> ListingPreviewOut:
    cleaned_text = text.strip()
    title = cleaned_text.splitlines()[0] if cleaned_text else None
    price, currency = _extract_price(cleaned_text)
    seller_details = _extract_seller_details(cleaned_text)
    description = "\n\n".join(
        [line for line in cleaned_text.splitlines()[1:] if line.strip()]
    ).strip()
    if not description:
        description = cleaned_text
    return _build_preview(title, price, currency, description, seller_details)


def _preview_from_html(html_text: str) -> ListingPreviewOut:
    cleaned_text = _clean_html_text(html_text)
    title = _extract_title(html_text, cleaned_text)
    description = _extract_description(html_text, cleaned_text)
    price, currency = _extract_price(cleaned_text)
    seller_details = _extract_seller_details(cleaned_text)
    return _build_preview(title, price, currency, description, seller_details)


def _resolve_public_ip(host: str) -> str:
    """Resolve `host` and return one public IP for the caller to connect
    to directly.

    Resolving via one lookup and connecting to that literal address (see
    `_fetch_url`) -- rather than validating a hostname and then letting
    httpx resolve and connect to that same hostname itself -- closes a
    DNS-rebinding window: an attacker's nameserver could otherwise return
    a public IP for this check and a private/loopback IP moments later
    when httpx does its own lookup to connect (PR #45 review, comment 1).
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise ValueError(f"Could not resolve host: {host}") from exc
    except UnicodeError as exc:
        raise ValueError(f"Invalid host: {host}") from exc

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

    raise ValueError("URL host resolves to a private or restricted address")


def _fetch_url(client: httpx.Client, url: str, deadline: float) -> httpx.Response:
    """Fetch a single hop of `url`, connecting to a freshly-resolved,
    validated IP rather than the hostname, without following redirects --
    the caller re-validates and re-resolves each hop itself. Following
    redirects automatically (the previous `follow_redirects=True` client)
    let a 3xx from an allowed public host redirect the fetch to a private
    address without ever re-checking it (PR #45 review, comment 1)."""
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES or not parsed.hostname:
        raise ValueError("Only http and https URLs are supported")

    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ValueError("URL fetch timed out")

    ip = _resolve_public_ip(parsed.hostname)
    pinned_host = f"[{ip}]" if ":" in ip else ip  # bracket IPv6 literals
    pinned_netloc = f"{pinned_host}:{parsed.port}" if parsed.port else pinned_host
    pinned_url = parsed._replace(netloc=pinned_netloc).geturl()

    # `read` capped separately so a slow trickle can't ride the full
    # remaining budget on every single chunk.
    timeout = httpx.Timeout(remaining, read=min(remaining, READ_CHUNK_TIMEOUT_SECONDS))
    request = client.build_request("GET", pinned_url, headers={"Host": parsed.hostname}, timeout=timeout)
    # Keep TLS certificate validation (and origin-side virtual-host
    # routing) working against the real hostname even though we connect
    # to its IP literal.
    request.extensions["sni_hostname"] = parsed.hostname

    return client.send(request, stream=True, follow_redirects=False)


def _fetch_html(url: str) -> str:
    deadline = time.monotonic() + FETCH_TIMEOUT_SECONDS
    next_url = url

    try:
        with httpx.Client(headers={"User-Agent": USER_AGENT}) as client:
            for _ in range(MAX_REDIRECTS + 1):
                resp = _fetch_url(client, next_url, deadline)
                with closing(resp):
                    if resp.is_redirect:
                        location = resp.headers.get("location")
                        if not location:
                            raise ValueError("Could not fetch URL: redirect missing Location")
                        next_url = urljoin(next_url, location)
                        continue

                    resp.raise_for_status()

                    # Streamed and size-checked incrementally -- checking
                    # len(response.content) only after a non-streaming
                    # client.get() had already downloaded everything
                    # defeated the point of a size cap (PR #45 review,
                    # comment 4).
                    body = bytearray()
                    for chunk in resp.iter_bytes():
                        body += chunk
                        if len(body) > MAX_FETCH_SIZE:
                            raise ValueError("URL response is too large to preview")
                        if time.monotonic() > deadline:
                            raise ValueError("URL fetch timed out")
                    return body.decode(resp.encoding or "utf-8", errors="ignore")
            raise ValueError("Too many redirects")
    except httpx.HTTPError as exc:
        # ConnectError/TimeoutException/HTTPStatusError/TooManyRedirects
        # etc. don't subclass ValueError, so without this the route's
        # `except ValueError` never catches them and a dead link or
        # timeout surfaces as an unhandled 500 (PR #45 review, comment 3).
        raise ValueError(f"Could not fetch URL: {exc}") from exc


def preview_listing_from_text(text: str) -> ListingPreviewOut:
    if not text or not text.strip():
        raise ValueError("Text preview requires non-empty text")
    return _preview_from_text(text)


def preview_listing_from_url(url: str) -> ListingPreviewOut:
    html_text = _fetch_html(url)
    return _preview_from_html(html_text)
