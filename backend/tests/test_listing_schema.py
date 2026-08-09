"""Unit tests for the listing service's input contract (ListingIn).

Workstream: E6 Testing & QA / E2 Listing Ingestion. These validate
app/schemas/schemas.py::ListingIn directly -- no DB, no HTTP -- covering
the rules POST /analyses relies on before any AI call is made (US-2.1).
"""
import pytest
from pydantic import ValidationError

from app.schemas.schemas import ListingIn

VALID_LISTING = {
    "title": "IKEA Billy bookcase, white",
    "price": 450.0,
    "currency": "zar",
    "source": "Facebook Marketplace",
    "description": "Used bookcase in good condition, collection in Randburg.",
}


def test_valid_listing_constructs():
    listing = ListingIn(**VALID_LISTING)
    assert listing.title == VALID_LISTING["title"]
    assert listing.url is None


def test_currency_is_uppercased():
    listing = ListingIn(**{**VALID_LISTING, "currency": "usd"})
    assert listing.currency == "USD"


@pytest.mark.parametrize("bad_currency", ["US", "USDD", "1SD", ""])
def test_invalid_currency_shape_rejected(bad_currency):
    with pytest.raises(ValidationError):
        ListingIn(**{**VALID_LISTING, "currency": bad_currency})


@pytest.mark.parametrize("bad_price", [0, -5, -0.01])
def test_non_positive_price_rejected(bad_price):
    with pytest.raises(ValidationError):
        ListingIn(**{**VALID_LISTING, "price": bad_price})


def test_positive_price_accepted():
    listing = ListingIn(**{**VALID_LISTING, "price": 0.01})
    assert listing.price == 0.01


def test_description_below_minimum_length_rejected():
    with pytest.raises(ValidationError):
        ListingIn(**{**VALID_LISTING, "description": "too short"})


def test_missing_required_field_rejected():
    incomplete = {k: v for k, v in VALID_LISTING.items() if k != "title"}
    with pytest.raises(ValidationError):
        ListingIn(**incomplete)


def test_url_optional_accepts_none():
    listing = ListingIn(**{**VALID_LISTING, "url": None})
    assert listing.url is None


def test_url_accepts_valid_http_url():
    listing = ListingIn(**{**VALID_LISTING, "url": "https://example.com/item/1"})
    assert str(listing.url) == "https://example.com/item/1"


def test_url_rejects_non_url_string():
    with pytest.raises(ValidationError):
        ListingIn(**{**VALID_LISTING, "url": "not a url"})


TINY_PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAA"


def test_images_default_to_empty_list():
    listing = ListingIn(**VALID_LISTING)
    assert listing.images == []


def test_valid_image_data_uri_accepted():
    listing = ListingIn(**{**VALID_LISTING, "images": [TINY_PNG]})
    assert listing.images == [TINY_PNG]


@pytest.mark.parametrize(
    "bad_image",
    [
        "not-a-data-uri",
        "data:text/plain;base64,aGVsbG8=",  # right shape, wrong mime type
        "data:image/png;base64,not valid base64!!",  # invalid base64 charset
        "https://example.com/photo.jpg",  # a URL, not a data URI
    ],
)
def test_invalid_image_format_rejected(bad_image):
    with pytest.raises(ValidationError):
        ListingIn(**{**VALID_LISTING, "images": [bad_image]})
