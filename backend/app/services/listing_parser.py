import html
import ipaddress
import re
import socket
from html import unescape
from urllib.parse import urlparse

import httpx

from app.schemas.schemas import ListingPreviewOut

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
    r"\bR(?P<number>\d{1,3}(?:[\,\d]*)(?:\.\d+)?)\b",
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

MAX_FETCH_SIZE = 200_000


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
    normalized = text.replace("\u00A0", " ")
    for pat in PRICE_PATTERNS:
        match = re.search(pat, normalized, re.I)
        if not match:
            continue
        number = match.groupdict().get("number")
        if not number:
            continue
        number = number.replace(",", "")
        try:
            amount = float(number)
        except ValueError:
            continue
        currency = None
        if match.groupdict().get("code"):
            currency = match.groupdict()["code"].upper()
        elif match.groupdict().get("symbol"):
            currency = PRICE_SYMBOL_MAP.get(match.groupdict()["symbol"])
        else:
            currency = None
        return amount, currency
    return None, None


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
    return ListingPreviewOut(
        title=title or None,
        price=price,
        currency=currency,
        description=description,
        seller_details=seller_details,
    )


def _preview_from_html(html_text: str) -> ListingPreviewOut:
    cleaned_text = _clean_html_text(html_text)
    title = _extract_title(html_text, cleaned_text)
    description = _extract_description(html_text, cleaned_text)
    price, currency = _extract_price(cleaned_text)
    seller_details = _extract_seller_details(cleaned_text)
    return ListingPreviewOut(
        title=title,
        price=price,
        currency=currency,
        description=description,
        seller_details=seller_details,
    )


def _is_private_address(hostname: str) -> bool:
    try:
        for family, _, _, _, sockaddr in socket.getaddrinfo(hostname, None):
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return True
    except socket.gaierror:
        return False
    return False


def _fetch_html(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http and https URLs are supported")
    host = parsed.hostname or ""
    if _is_private_address(host):
        raise ValueError("URL host resolves to a private or restricted address")

    with httpx.Client(follow_redirects=True, timeout=10.0) as client:
        response = client.get(url, headers={"User-Agent": "TrustAI Marketplace URL Preview"})
        response.raise_for_status()
        if len(response.content) > MAX_FETCH_SIZE:
            raise ValueError("URL response is too large to preview")
        return response.text


def preview_listing_from_text(text: str) -> ListingPreviewOut:
    if not text or not text.strip():
        raise ValueError("Text preview requires non-empty text")
    return _preview_from_text(text)


def preview_listing_from_url(url: str) -> ListingPreviewOut:
    html_text = _fetch_html(url)
    return _preview_from_html(html_text)
